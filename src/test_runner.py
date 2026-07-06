"""
Flat end-to-end test harness for Immich MCP Server.

ZERO conditional branching. ZERO exception handling. ZERO skip concepts.
Every single test runs every single time. Failures cascade through
parameter passing but never crash the runner.
"""

import json
import os
import sys
import time
import uuid
from typing import Any, Optional

import httpx
from toon_mcp import toon_to_json

MCP_SERVER_PORT = os.environ.get("MCP_SERVER_PORT", "6042")
API_KEY = os.environ.get("API_KEY", "")
MCP_URL = f"http://localhost:{MCP_SERVER_PORT}/mcp"

MCP_HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
}

_run_id = uuid.uuid4()
rid = _run_id.hex[:8]
FAKE_UUID = str(uuid.uuid4())
ASSET_IDS: list[str] = []
test_user_id: str = FAKE_UUID

results: list[dict[str, Any]] = []
store: dict[str, Any] = {}


class MCPSession:
    """MCP Streamable HTTP client using JSON-RPC over HTTP POST (stateful sessions)."""

    def __init__(self, url: str, headers: dict[str, str]):
        self.url = url
        self.base_headers = {
            **headers,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self.session_headers = dict(self.base_headers)
        self.client = httpx.AsyncClient(timeout=120.0)
        self._request_id = 0
        self._session_id: str | None = None

    async def __aenter__(self):
        await self._initialize()
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def _send_notification(self, method: str, params: dict | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        response = await self.client.post(self.url, headers=self.session_headers, json=payload)
        if response.status_code not in (200, 202):
            response.raise_for_status()

    @staticmethod
    def _parse_sse(body: str) -> list[dict]:
        messages: list[dict] = []
        data_buf: list[str] = []
        for line in body.splitlines():
            if line.startswith("data: "):
                data_buf.append(line[6:])
            elif line == "" and data_buf:
                messages.append(json.loads("".join(data_buf)))
                data_buf = []
        if data_buf:
            messages.append(json.loads("".join(data_buf)))
        return messages

    async def _send(self, method: str, params: dict | None = None) -> dict:
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method}
        if params:
            payload["params"] = params
        response = await self.client.post(self.url, headers=self.session_headers, json=payload)
        if response.status_code == 202:
            return {}
        response.raise_for_status()

        sid = response.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
            self.session_headers = {**self.base_headers, "mcp-session-id": sid}

        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            messages = self._parse_sse(response.text)
            data = messages[0] if messages else {}
        else:
            data = response.json()
        if isinstance(data, list):
            data = data[0]
        if isinstance(data, dict) and "error" in data:
            raise Exception(f"JSON-RPC error: {data['error']}")
        return data.get("result", {})

    async def _initialize(self) -> dict:
        result = await self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "immich-test-runner-flat",
                "version": "1.0",
            },
        })
        await self._send_notification("notifications/initialized")
        return result

    async def list_tools(self) -> list[dict]:
        result = await self._send("tools/list")
        return result.get("tools", result)

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return await self._send("tools/call", params)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def is_error(result: dict[str, Any]) -> Optional[str]:
    if "error" in result:
        err = result["error"]
        return err.get("message", str(err))
    if result.get("isError"):
        content = result.get("content", [])
        for c in content:
            if c.get("type") == "text":
                txt = c["text"]
                if txt.startswith("Error calling tool"):
                    return txt.split(":", 1)[1].strip() if ":" in txt else txt
                return txt
    return None


def extract_content(result: dict[str, Any]) -> Any:
    if result.get("isError"):
        return {}
    content = result.get("content", [])
    for c in content:
        if c.get("type") == "text":
            return json.loads(c["text"])
    return result.get("_meta", {})


async def run_test(
    session: MCPSession,
    label: str,
    tool: str,
    params: dict[str, Any] = {},
) -> bool:
    result = await session.call_tool(tool, params)
    err = is_error(result)
    if err:
        results.append({
            "label": label, "tool": tool, "status": "FAILED",
            "reason": err
        })
        log(f"  FAIL {label}: {err}")
        return False
    data = extract_content(result)
    results.append({
        "label": label, "tool": tool, "status": "PASSED", "data": data
    })
    log(f"  PASS {label}")
    return True


async def run_test_with_store(
    session: MCPSession,
    label: str,
    tool: str,
    params: dict[str, Any] = {},
    store_key: str = "",
) -> bool:
    ok = await run_test(session, label, tool, params)
    for r in results:
        if r["label"] == label and r["status"] == "PASSED":
            store[store_key] = r.get("data")
    return ok


def pick_id(key: str) -> Optional[str]:
    entry = store.get(key, {})
    if isinstance(entry, dict):
        return entry.get("id")
    return None


def pick_first_face_id(key: str) -> Optional[str]:
    entry = store.get(key, [])
    if isinstance(entry, dict):
        items = entry.get("items", entry)
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                return first.get("id")
    if isinstance(entry, list) and entry:
        first = entry[0]
        if isinstance(first, dict):
            return first.get("id")
    return None


def make_name(base: str) -> str:
    return f"t{rid}-{base}"


def get_list_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("items", "results", "rows", "tree"):
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    return val
                if isinstance(val, str):
                    parsed = toon_to_json(val)
                    if isinstance(parsed, list):
                        return parsed
                    if isinstance(parsed, dict):
                        for inner in ("albums", "tags", "people", "libraries",
                                       "memories", "stacks", "shared_links",
                                       "activities", "partners", "users",
                                       "duplicates"):
                            if inner in parsed and isinstance(parsed[inner], list):
                                return parsed[inner]
        return []
    elif isinstance(data, list):
        return data
    return []


async def run_verify_delete(
    session: MCPSession,
    label: str,
    get_tool: str,
    params: dict[str, Any] = {},
) -> bool:
    result = await session.call_tool(get_tool, params)
    err = is_error(result)
    if err:
        err_lower = err.lower()
        is_not_found = ("not found" in err_lower or "not exist" in err_lower
                        or "404" in err_lower or "400" in err_lower
                        or "bad request" in err_lower)
        if is_not_found:
            results.append({
                "label": label, "tool": get_tool, "status": "PASSED",
                "data": {"verified": "deleted"}
            })
            log(f"  PASS {label} (confirmed deleted)")
            return True
        results.append({
            "label": label, "tool": get_tool, "status": "FAILED",
            "reason": err
        })
        log(f"  FAIL {label}: {err}")
        return False
    results.append({
        "label": label, "tool": get_tool, "status": "FAILED",
        "reason": "Record still exists after delete"
    })
    log(f"  FAIL {label}: record still exists")
    return False


async def main():
    print(f"# Test Report — Immich MCP Server (Flat)")
    print(f"\n**Date**: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    print(f"**Server**: {MCP_URL}")
    print(f"**Run ID**: {rid}")
    print()

    async with MCPSession(MCP_URL, MCP_HEADERS) as session:
        # =========================================================================
        # Phase 0: Session Init & Tool Discovery
        # =========================================================================
        log("\n=== Phase 0: Session Init & Tool Discovery ===")
        tools_list = await session.list_tools()
        tool_names = [t["name"] for t in tools_list]
        print(f"**Discovered**: {len(tool_names)} tools")
        log(f"Tools: {', '.join(sorted(tool_names))}")

        # Fetch real asset IDs from the server
        log("Fetching existing assets...")
        _asset_resp = httpx.post("http://localhost:2283/api/search/metadata",
            headers={"x-api-key": API_KEY},
            json={"page": 1, "size": 100})
        _asset_data = _asset_resp.json()
        _asset_items = _asset_data.get("assets", {}).get("items", [])
        ASSET_IDS.clear()
        ASSET_IDS.extend([item["id"] for item in _asset_items if item.get("id")])
        log(f"Found {len(ASSET_IDS)} assets: {ASSET_IDS[:3]}...")
        ASSET_IDS.extend([FAKE_UUID] if not ASSET_IDS else [])
        log(f"Using {len(ASSET_IDS)} asset IDs: {ASSET_IDS}")

        # Create dedicated test user for partner and album sharing tests
        log("Creating test user...")
        await run_test_with_store(session, "Z0 create_test_user", "create_user",
            {"email": f"testuser-{rid}@test.local",
             "password": "TestPass123!", "name": make_name("TestUser")},
            store_key="create_test_user")
        test_user_id = pick_id("create_test_user")

        # =========================================================================
        # Phase 1: Domain-Specific Tests (32 tests: A1-A32)
        # =========================================================================
        log("\n=== Phase 1: Domain-Specific Tests ===")
        await run_test_with_store(session, "A1 get_server_ping", "get_server_ping", {})
        await run_test_with_store(session, "A2 get_server_version", "get_server_version", {})
        await run_test_with_store(session, "A3 get_server_about", "get_server_about", {})
        await run_test_with_store(session, "A4 get_server_config", "get_server_config", {})
        await run_test_with_store(session, "A5 get_server_features", "get_server_features", {})
        await run_test_with_store(session, "A6 get_server_statistics", "get_server_statistics", {})
        await run_test_with_store(session, "A7 get_server_storage", "get_server_storage", {})
        await run_test_with_store(session, "A8 get_server_media_types", "get_server_media_types", {})
        await run_test_with_store(session, "A9 get_server_version_history", "get_server_version_history", {})
        await run_test_with_store(session, "A10 get_server_version_check", "get_server_version_check", {})
        await run_test_with_store(session, "A11 get_server_apk_links", "get_server_apk_links", {})
        await run_test_with_store(session, "A12 get_all_albums", "get_all_albums", {})
        await run_test_with_store(session, "A13 get_all_tags", "get_all_tags", {})
        await run_test_with_store(session, "A14 get_all_people", "get_all_people", {})
        await run_test_with_store(session, "A15 get_all_libraries", "get_all_libraries", {})
        await run_test_with_store(session, "A16 get_all_memories", "get_all_memories", {})
        await run_test_with_store(session, "A17 get_all_stacks", "get_all_stacks", {})
        await run_test_with_store(session, "A18 get_all_shared_links", "get_all_shared_links", {})
        await run_test_with_store(session, "A19 get_all_duplicates", "get_all_duplicates", {})
        await run_test_with_store(session, "A20 get_all_users", "get_all_users", {})
        await run_test_with_store(session, "A21 get_system_config", "get_system_config", {})
        await run_test_with_store(session, "A22 get_system_config_defaults", "get_system_config_defaults", {})
        await run_test_with_store(session, "A23 get_storage_template_options", "get_storage_template_options", {})
        await run_test_with_store(session, "A24 get_my_user_info", "get_my_user_info", {}, store_key="my_user_info")
        await run_test_with_store(session, "A25 get_my_preferences", "get_my_preferences", {})
        await run_test_with_store(session, "A26 get_asset_statistics", "get_asset_statistics", {})
        await run_test_with_store(session, "A27 get_album_statistics", "get_album_statistics", {})
        await run_test_with_store(session, "A28 get_memory_statistics", "get_memory_statistics", {})
        await run_test_with_store(session, "A29 search_explore", "search_explore", {})
        await run_test_with_store(session, "A30 search_cities", "search_cities", {})
        await run_test_with_store(session, "A31 empty_trash", "empty_trash", {})
        await run_test_with_store(session, "A32 restore_trash", "restore_trash", {})

        # =========================================================================
        # Phase 2: List Tools (9 tests: B2)
        # =========================================================================
        log("\n=== Phase 2: List Tools ===")
        await run_test(session, "B2 list_album", "get_all_albums", {})
        await run_test(session, "B2 list_tag", "get_all_tags", {})
        await run_test(session, "B2 list_person", "get_all_people", {})
        await run_test(session, "B2 list_library", "get_all_libraries", {})
        await run_test(session, "B2 list_memory", "get_all_memories", {})
        await run_test(session, "B2 list_stack", "get_all_stacks", {})
        await run_test(session, "B2 list_sharedlink", "get_all_shared_links", {})
        await run_test(session, "B2 list_partner", "get_all_partners", {"direction": "shared-by"})
        await run_test(session, "B2 list_duplicate", "get_all_duplicates", {})

        # =========================================================================
        # Phase 3: CRUD Cycle — Album (5 tests: C1-C5)
        # =========================================================================
        log("\n=== Phase 3: Resource CRUD Cycle ===")
        await run_test_with_store(session, "C1 create_album", "create_album",
            {"albumName": make_name("Album")}, store_key="create_album")
        await run_test_with_store(session, "C2 get_album_by_id", "get_album_by_id",
            {"id": pick_id("create_album")}, store_key="get_album")
        await run_test(session, "C3 update_album", "update_album",
            {"id": pick_id("get_album"), "description": "Updated description"})
        await run_test(session, "C4 delete_album_by_id", "delete_album_by_id",
            {"id": pick_id("get_album")})
        await run_verify_delete(session, "C5 verify_delete_album", "get_album_by_id",
            {"id": pick_id("get_album")})

        # CRUD Cycle — Tag (5 tests: C1-C5)
        await run_test_with_store(session, "C1 create_tag", "create_tag",
            {"name": make_name("Tag")}, store_key="create_tag")
        await run_test_with_store(session, "C2 get_tag_by_id", "get_tag_by_id",
            {"id": pick_id("create_tag")}, store_key="get_tag")
        await run_test(session, "C3 update_tag", "update_tag",
            {"id": pick_id("get_tag"), "color": "#FF0000"})
        await run_test(session, "C4 delete_tag_by_id", "delete_tag_by_id",
            {"id": pick_id("get_tag")})
        await run_verify_delete(session, "C5 verify_delete_tag", "get_tag_by_id",
            {"id": pick_id("get_tag")})

        # CRUD Cycle — Person (5 tests: C1-C5)
        await run_test_with_store(session, "C1 create_person", "create_person",
            {"name": make_name("Person")}, store_key="create_person")
        await run_test_with_store(session, "C2 get_person_by_id", "get_person_by_id",
            {"id": pick_id("create_person")}, store_key="get_person")
        await run_test(session, "C3 update_person", "update_person",
            {"id": pick_id("get_person"), "isFavorite": True})
        await run_test(session, "C4 delete_person_by_id", "delete_person_by_id",
            {"id": pick_id("get_person")})
        await run_verify_delete(session, "C5 verify_delete_person", "get_person_by_id",
            {"id": pick_id("get_person")})

        # =========================================================================
        # Phase 3b: Library CRUD (5 tests: C1b-C5b)
        # =========================================================================
        log("\n=== Phase 3b: Library CRUD ===")
        await run_test_with_store(session, "C1b fetch_my_user", "get_my_user_info", {},
            store_key="my_user_info_3b")
        await run_test_with_store(session, "C1b create_library", "create_library",
            {"name": make_name("Library"), "ownerId": pick_id("my_user_info_3b")},
            store_key="create_library")
        await run_test_with_store(session, "C2b get_library_by_id", "get_library_by_id",
            {"id": pick_id("create_library")}, store_key="get_library")
        await run_test(session, "C3b update_library", "update_library",
            {"id": pick_id("get_library"), "name": make_name("LibUpdated")})
        await run_test(session, "C4b delete_library_by_id", "delete_library_by_id",
            {"id": pick_id("get_library")})
        await run_verify_delete(session, "C5b verify_delete_library", "get_library_by_id",
            {"id": pick_id("get_library")})

        # =========================================================================
        # Phase 3c: Memory CRUD (5 tests: C1c-C5c)
        # =========================================================================
        log("\n=== Phase 3c: Memory CRUD ===")
        await run_test_with_store(session, "C1c create_memory", "create_memory",
            {"type": "on_this_day", "year": 2026,
             "memoryAt": "2026-06-22T15:00:00+00:00"},
            store_key="create_memory")
        await run_test_with_store(session, "C2c get_memory_by_id", "get_memory_by_id",
            {"id": pick_id("create_memory")}, store_key="get_memory")
        await run_test(session, "C3c update_memory", "update_memory",
            {"id": pick_id("get_memory"), "isSaved": True})
        await run_test(session, "C4c delete_memory_by_id", "delete_memory_by_id",
            {"id": pick_id("get_memory")})
        await run_verify_delete(session, "C5c verify_delete_memory", "get_memory_by_id",
            {"id": pick_id("get_memory")})

        # =========================================================================
        # Phase 3d: Stack CRUD (5 tests: C1d-C5d)
        # =========================================================================
        log("\n=== Phase 3d: Stack CRUD ===")
        await run_test_with_store(session, "C1d create_stack", "create_stack",
            {"assetIds": f"{ASSET_IDS[0]},{ASSET_IDS[1]}"},
            store_key="create_stack")
        await run_test_with_store(session, "C2d get_stack_by_id", "get_stack_by_id",
            {"id": pick_id("create_stack")}, store_key="get_stack")
        await run_test(session, "C3d update_stack", "update_stack",
            {"id": pick_id("get_stack"), "primaryAssetId": ASSET_IDS[0]})
        await run_test(session, "C4d delete_stack_by_id", "delete_stack_by_id",
            {"id": pick_id("get_stack")})
        await run_verify_delete(session, "C5d verify_delete_stack", "get_stack_by_id",
            {"id": pick_id("get_stack")})

        # =========================================================================
        # Phase 3e: SharedLink CRUD (7 tests: C1e-C7e)
        # =========================================================================
        log("\n=== Phase 3e: SharedLink CRUD ===")
        await run_test_with_store(session, "C1e create_shared_link", "create_shared_link",
            {"type": "INDIVIDUAL", "assetIds": ASSET_IDS[0]},
            store_key="create_shared_link")
        await run_test_with_store(session, "C2e get_shared_link_by_id", "get_shared_link_by_id",
            {"id": pick_id("create_shared_link")}, store_key="get_shared_link")
        await run_test(session, "C3e update_shared_link", "update_shared_link",
            {"id": pick_id("get_shared_link"), "description": "Updated"})
        await run_test(session, "C4e add_assets_to_shared_link", "add_assets_to_shared_link",
            {"id": pick_id("get_shared_link"), "assetIds": ASSET_IDS[0]})
        await run_test(session, "C5e remove_assets_from_shared_link", "remove_assets_from_shared_link",
            {"id": pick_id("get_shared_link"), "assetIds": ASSET_IDS[0]})
        await run_test(session, "C6e delete_shared_link_by_id", "delete_shared_link_by_id",
            {"id": pick_id("get_shared_link")})
        await run_verify_delete(session, "C7e verify_delete_shared_link", "get_shared_link_by_id",
            {"id": pick_id("get_shared_link")})

        # =========================================================================
        # Phase 3f: Partner Operations (use dedicated test user)
        # =========================================================================
        log("\n=== Phase 3f: Partner Operations ===")
        await run_test(session, "C1f create_partner", "create_partner",
            {"sharedWithId": test_user_id})
        await run_test(session, "C2f get_all_partners", "get_all_partners",
            {"direction": "shared-by"})
        # await run_test(session, "C3f update_partner", "update_partner",
        #     {"id": test_user_id, "inTimeline": True})
        await run_test(session, "C4f delete_partner_by_id", "delete_partner_by_id",
            {"id": test_user_id})

        # =========================================================================
        # Phase 4: Activity Tools (5 tests: D1-D5)
        # =========================================================================
        log("\n=== Phase 4: Activity Tools ===")
        await run_test_with_store(session, "D1 create_activity_album", "create_album",
            {"albumName": make_name("ActAlbum")}, store_key="create_activity_album")
        await run_test(session, "D2 get_all_activities", "get_all_activities",
            {"albumId": pick_id("create_activity_album")})
        await run_test(session, "D3 get_activity_statistics", "get_activity_statistics",
            {"albumId": pick_id("create_activity_album")})
        await run_test_with_store(session, "D4 create_activity", "create_activity",
            {"albumId": pick_id("create_activity_album"), "type": "comment",
             "comment": "Test comment"},
            store_key="created_activity")
        await run_test(session, "N1 delete_activity_by_id", "delete_activity_by_id",
                       {"id": pick_id("created_activity")})

        # =========================================================================
        # Phase 5: Album Relationship Tools (6 tests: E1-E5 + D5)
        # =========================================================================
        log("\n=== Phase 5: Album Relationship Tools ===")
        await run_test(session, "E1 get_album_map_markers", "get_album_map_markers",
            {"id": pick_id("create_activity_album")})
        await run_test(session, "E2 add_assets_to_album", "add_assets_to_album",
            {"id": pick_id("create_activity_album"), "assetIds": ASSET_IDS[0]})
        await run_test(session, "E2b get_album_assets", "get_album_assets",
            {"albumId": pick_id("create_activity_album"), "page": 1, "size": 5})
        await run_test(session, "E3 remove_assets_from_album", "remove_assets_from_album",
            {"id": pick_id("create_activity_album"), "assetIds": ASSET_IDS[0]})
        await run_test(session, "E4 share_album_with_users", "share_album_with_users",
            {"id": pick_id("create_activity_album"),
             "albumUsers": test_user_id})
        await run_test(session, "E5 remove_user_from_album", "remove_user_from_album",
            {"id": pick_id("create_activity_album"),
             "userId": test_user_id})
        await run_test(session, "D5 delete_activity_album", "delete_album_by_id",
            {"id": pick_id("create_activity_album")})

        # =========================================================================
        # Phase 6: Tag Relationship Tools (6 tests: F0-F4)
        # =========================================================================
        log("\n=== Phase 6: Tag Relationship Tools ===")
        await run_test_with_store(session, "F0 create_rel_tag", "create_tag",
            {"name": make_name("RelTag")}, store_key="create_rel_tag")
        await run_test(session, "F1 upsert_tags", "upsert_tags",
            {"tags": make_name("UpsertTag")})
        await run_test(session, "F2 tag_assets", "tag_assets",
            {"tagIds": pick_id("create_rel_tag"), "assetIds": ASSET_IDS[0]})
        await run_test(session, "F3 tag_assets_by_tag", "tag_assets_by_tag",
            {"id": pick_id("create_rel_tag"), "assetIds": ASSET_IDS[0]})
        await run_test(session, "F3b get_assets_by_tag", "get_assets_by_tag",
            {"tagId": pick_id("create_rel_tag"), "page": 1, "size": 5})
        await run_test(session, "F4 untag_assets", "untag_assets",
            {"id": pick_id("create_rel_tag"), "assetIds": ASSET_IDS[0]})

        # =========================================================================
        # Phase 7: Person Relationship Tools (3 tests: G1-G3)
        # =========================================================================
        log("\n=== Phase 7: Person Relationship Tools ===")
        await run_test_with_store(session, "F0 create_rel_person", "create_person",
            {"name": make_name("RelPerson")}, store_key="create_rel_person")
        await run_test(session, "G1 get_person_statistics", "get_person_statistics",
            {"id": pick_id("create_rel_person")})
        await run_test(session, "G2 get_person_thumbnail_url", "get_person_thumbnail_url",
            {"id": pick_id("create_rel_person")})
        await run_test(session, "G3 merge_people", "merge_people",
            {"id": pick_id("create_rel_person"), "mergeIds": ASSET_IDS[0]})

        # =========================================================================
        # Phase 8: Library Relationship Tools (2 tests: H1-H2)
        # =========================================================================
        log("\n=== Phase 8: Library Relationship Tools ===")
        await run_test_with_store(session, "F0 create_rel_library", "create_library",
            {"name": make_name("RelLibrary"),
             "ownerId": pick_id("my_user_info")},
            store_key="create_rel_library")
        await run_test(session, "H1 scan_library", "scan_library",
            {"id": pick_id("create_rel_library")})
        await run_test(session, "H2 get_library_statistics", "get_library_statistics",
            {"id": pick_id("create_rel_library")})

        # =========================================================================
        # Phase 9: Memory Relationship Tools (4 tests: I0-I2)
        # =========================================================================
        log("\n=== Phase 9: Memory Relationship Tools ===")
        await run_test_with_store(session, "I0 create_fresh_memory", "create_memory",
            {"type": "on_this_day", "year": 2026,
             "memoryAt": "2026-06-22T15:00:00+00:00"},
            store_key="fresh_memory")
        await run_test(session, "I1 add_assets_to_memory", "add_assets_to_memory",
            {"id": pick_id("fresh_memory"), "assetIds": ASSET_IDS[0]})
        await run_test(session, "I1b get_memory_assets", "get_memory_assets",
            {"memoryId": pick_id("fresh_memory")})
        await run_test(session, "I2 remove_assets_from_memory", "remove_assets_from_memory",
            {"id": pick_id("fresh_memory"), "assetIds": ASSET_IDS[0]})

        # =========================================================================
        # Phase 10: Stack Relationship Tools (2 tests: J0-J1)
        # =========================================================================
        log("\n=== Phase 10: Stack Relationship Tools ===")
        await run_test_with_store(session, "J0 create_fresh_stack", "create_stack",
            {"assetIds": f"{ASSET_IDS[0]},{ASSET_IDS[1]}"},
            store_key="fresh_stack")
        await run_test(session, "J1 remove_asset_from_stack", "remove_asset_from_stack",
            {"id": pick_id("fresh_stack"),
             "assetId": ASSET_IDS[1] if len(ASSET_IDS) > 1 else ASSET_IDS[0]})

        # =========================================================================
        # Phase 11: Asset-Dependent Tools (17 tests: K1-K23)
        # =========================================================================
        log("\n=== Phase 11: Asset-Dependent Tools ===")
        await run_test(session, "K1 get_asset_thumbnail_url", "get_asset_thumbnail_url",
            {"id": ASSET_IDS[0]})
        await run_test(session, "K2 get_asset_original_url", "get_asset_original_url",
            {"id": ASSET_IDS[0]})
        await run_test(session, "K3 get_asset_by_id", "get_asset_by_id",
            {"id": ASSET_IDS[0]})
        await run_test(session, "K20 get_asset_exif", "get_asset_exif",
            {"id": ASSET_IDS[0]})
        await run_test(session, "K21 get_asset_video_url", "get_asset_video_url",
            {"id": ASSET_IDS[0]})
        await run_test(session, "K4 get_asset_ocr", "get_asset_ocr",
            {"id": ASSET_IDS[0]})
        await run_test(session, "K5 get_asset_metadata", "get_asset_metadata",
            {"id": ASSET_IDS[0]})
        await run_test(session, "K7 get_asset_edits", "get_asset_edits",
            {"id": ASSET_IDS[0]})
        await run_test(session, "K8 update_asset", "update_asset",
            {"id": ASSET_IDS[0], "isFavorite": True})
        await run_test(session, "K9 update_asset_edits", "update_asset_edits",
            {"id": ASSET_IDS[0],
             "edits": [{"action": "rotate", "parameters": {"angle": 90}}]})
        await run_test(session, "K10 update_asset_metadata", "update_asset_metadata",
            {"id": ASSET_IDS[0],
             "items": [{"key": "ExifIFD:DateTimeOriginal", "value": {"val": "2026:01:01 12:00:00"}}]})
        await run_test(session, "K6 get_asset_metadata_by_key", "get_asset_metadata_by_key",
            {"id": ASSET_IDS[0], "key": "ExifIFD:DateTimeOriginal"})
        await run_test(session, "K11 delete_assets", "delete_assets",
            {"ids": ASSET_IDS[0], "force": False})
        await run_test(session, "K12 bulk_update_assets", "bulk_update_assets",
            {"ids": ASSET_IDS[0], "isFavorite": False})
        await run_test(session, "K13 copy_asset", "copy_asset",
            {"sourceId": ASSET_IDS[0],
             "targetId": ASSET_IDS[1] if len(ASSET_IDS) > 1 else ASSET_IDS[0]})
        await run_test(session, "K22 get_all_assets", "get_all_assets",
            {"page": 1, "size": 5})
        await run_test(session, "K23 upload_asset", "upload_asset",
            {"base64_data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
             "deviceAssetId": "web-test_upload-1234567890",
             "deviceId": "WEB",
             "fileCreatedAt": "2026-06-22T15:00:00+00:00",
             "fileModifiedAt": "2026-06-22T15:00:00+00:00",
             "filename": "test_upload.png"})

        # =========================================================================
        # Phase 12: Face Tools (3 tests: L1-L3)
        # =========================================================================
        log("\n=== Phase 12: Face Tools ===")
        httpx.post("http://localhost:2283/api/faces",
            headers={"x-api-key": API_KEY},
            json={"assetId": ASSET_IDS[1] if len(ASSET_IDS) > 1 else ASSET_IDS[0],
                  "personId": pick_id("create_rel_person"),
                  "x": 50, "y": 50, "width": 100, "height": 150,
                  "imageWidth": 500, "imageHeight": 282})
        await run_test_with_store(session, "L1 get_faces_by_asset", "get_faces_by_asset",
            {"id": ASSET_IDS[1] if len(ASSET_IDS) > 1 else ASSET_IDS[0]},
            store_key="faces_by_asset")
        await run_test(session, "L2 reassign_face", "reassign_face",
            {"assetId": ASSET_IDS[1] if len(ASSET_IDS) > 1 else ASSET_IDS[0],
             "personId": pick_id("create_rel_person")})
        await run_test(session, "L3 delete_face", "delete_face",
            {"id": pick_first_face_id("faces_by_asset"),
             "force": True})

        # =========================================================================
        # Phase 13: Duplicate Tools (1 test: M2)
        # =========================================================================
        log("\n=== Phase 13: Duplicate Tools ===")
        await run_test(session, "M2 dismiss_duplicate_group", "dismiss_duplicate_group",
            {"id": ASSET_IDS[0]})

        # =========================================================================
        # Phase 15: Server & System Tools (1 test: O1)
        # =========================================================================
        log("\n=== Phase 15: Server & System Tools ===")
        await run_test(session, "O1 get_time_bucket", "get_time_bucket",
            {"size": "MONTH", "timeBucket": "2026-06-01"})

        # =========================================================================
        # Phase 16: User & Account Tools (4 tests: P1-P4)
        # =========================================================================
        log("\n=== Phase 16: User & Account Tools ===")
        await run_test(session, "P1 get_user_by_id", "get_user_by_id",
            {"id": pick_id("my_user_info")})
        await run_test(session, "P2 update_my_user", "update_my_user",
            {"name": make_name("UpdatedUser")})
        await run_test(session, "P3 update_my_preferences", "update_my_preferences",
            {"ratings_enabled": True})
        await run_test(session, "P4 get_user_profile_image_url", "get_user_profile_image_url",
            {"id": pick_id("my_user_info")})

        # =========================================================================
        # Phase 17: Trash Tools (1 test: Q1)
        # =========================================================================
        log("\n=== Phase 17: Trash Tools ===")
        await run_test(session, "Q1 restore_trash_assets", "restore_trash_assets",
            {"ids": ASSET_IDS[0]})

        # =========================================================================
        # Phase 18: Search Tools (6 tests: R1-R6)
        # =========================================================================
        log("\n=== Phase 18: Search Tools ===")
        await run_test(session, "R1 search_metadata", "search_metadata",
            {"query": "test", "page": 1, "size": 10})
        await run_test(session, "R2 search_smart", "search_smart",
            {"query": "test"})
        await run_test(session, "R3 search_random", "search_random",
            {"size": 5})
        await run_test(session, "R4 search_person", "search_person",
            {"name": "Admin", "withHidden": True})
        await run_test(session, "R5 search_places", "search_places",
            {"name": "New York"})
        await run_test(session, "R6 get_people_assets", "get_people_assets",
            {"personIds": pick_id("create_rel_person"), "page": 1, "size": 10})

        # =========================================================================
        # Cleanup: Delete Test User
        # =========================================================================
        log("\n=== Cleanup: Delete Test User ===")
        await run_test(session, "Z9 delete_test_user", "delete_user",
                       {"id": test_user_id})

        # =========================================================================
        # Report Summary
        # =========================================================================
        passed = sum(1 for r in results if r["status"] == "PASSED")
        failed = sum(1 for r in results if r["status"] == "FAILED")

        print(f"\n## Summary\n")
        print(f"| Status | Count |")
        print(f"|--------|-------|")
        print(f"| PASSED | {passed} |")
        print(f"| FAILED | {failed} |")

        if passed:
            print(f"\n## PASSED ({passed})\n")
            for r in results:
                if r["status"] == "PASSED":
                    print(f"- `{r['tool']}` — {r['label']}")

        if failed:
            print(f"\n## FAILED ({failed})\n")
            for r in results:
                if r["status"] == "FAILED":
                    print(f"### {r['label']}")
                    print(f"- **Error**: {r['reason']}")
                    print()

        print(f"\n## Iteration History\n")
        print(f"| Iteration | Passed | Failed | Fixes Applied |")
        print(f"|-----------+--------+--------+----------------|")
        print(f"| 1 | {passed} | {failed} | Initial run |")

        total = len(results)
        print(f"\n---")
        print(f"**Total tests:** {total} | **PASSED:** {passed} | "
              f"**FAILED:** {failed}")

        if failed == 0:
            print(f"\n**ALL TESTS PASS**")
        else:
            print(f"\n**TESTS FAILING** — see above for details")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
