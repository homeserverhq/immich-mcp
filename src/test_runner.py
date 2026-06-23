"""
End-to-end test harness for Immich MCP Server.

Connects via Streamable HTTP (JSON-RPC POST), tests all tools,
and prints a Markdown report to stdout.

Every test runs unconditionally — there is no SKIPPED status.
Tests exist to find flaws in main.py and client.py; the developer
fixes application code so that tests pass as a consequence.
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

results: list[dict[str, Any]] = []
store: dict[str, Any] = {}
created: dict[str, str] = {}





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
                "name": "immich-test-runner",
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
                try:
                    data = json.loads(txt)
                except json.JSONDecodeError:
                    return txt
                if isinstance(data, dict):
                    return data.get("error", txt)
    return None


def extract_content(result: dict[str, Any]) -> Any:
    if result.get("isError"):
        return {}
    content = result.get("content", [])
    for c in content:
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except json.JSONDecodeError:
                return c["text"]
    return result.get("_meta", {})


async def run_test(
    session: MCPSession,
    label: str,
    tool: str,
    params: dict[str, Any] = None,
) -> bool:
    if params is None:
        params = {}
    try:
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
    except Exception as e:
        results.append({
            "label": label, "tool": tool, "status": "FAILED",
            "reason": str(e)
        })
        log(f"  FAIL {label}: {e}")
        return False


async def run_test_with_store(
    session: MCPSession,
    label: str,
    tool: str,
    params: dict[str, Any] = None,
    store_key: str = None,
) -> bool:
    ok = await run_test(session, label, tool, params)
    if ok and store_key:
        for r in results:
            if r["label"] == label and r["status"] == "PASSED":
                store[store_key] = r.get("data")
                break
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
                    try:
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
                    except Exception:
                        pass
        return []
    elif isinstance(data, list):
        return data
    return []


async def run_verify_delete(
    session: MCPSession,
    label: str,
    get_tool: str,
    params: dict[str, Any] = None,
) -> bool:
    if params is None:
        params = {}
    try:
        result = await session.call_tool(get_tool, params)
        err = is_error(result)
        if err:
            if any(kw in err.lower() for kw in ("not found", "not exist", "404", "400", "bad request")):
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
    except Exception as e:
        results.append({
            "label": label, "tool": get_tool, "status": "FAILED",
            "reason": str(e)
        })
        log(f"  FAIL {label}: {e}")
        return False


# =============================================================================
# Test Data Configuration
# =============================================================================

RESOURCE_TESTS = [
    ("Album", "create_album",
     {"albumName": make_name("Album")},
     "get_all_albums", "get_album_by_id",
     "update_album", {"description": "Updated description"},
     "delete_album_by_id"),
    ("Tag", "create_tag",
     {"name": make_name("Tag")},
     "get_all_tags", "get_tag_by_id",
     "update_tag", {"color": "#FF0000"},
     "delete_tag_by_id"),
    ("Person", "create_person",
     {"name": make_name("Person")},
     "get_all_people", "get_person_by_id",
     "update_person", {"isFavorite": True},
     "delete_person_by_id"),
]

DOMAIN_TESTS = [
    ("get_server_ping", {}),
    ("get_server_version", {}),
    ("get_server_about", {}),
    ("get_server_config", {}),
    ("get_server_features", {}),
    ("get_server_statistics", {}),
    ("get_server_storage", {}),
    ("get_server_media_types", {}),
    ("get_server_version_history", {}),
    ("get_server_version_check", {}),
    ("get_server_apk_links", {}),
    ("get_all_albums", {}),
    ("get_all_tags", {}),
    ("get_all_people", {}),
    ("get_all_libraries", {}),
    ("get_all_memories", {}),
    ("get_all_stacks", {}),
    ("get_all_shared_links", {}),
    ("get_all_duplicates", {}),
    ("get_all_users", {}),
    ("get_system_config", {}),
    ("get_system_config_defaults", {}),
    ("get_storage_template_options", {}),
    ("get_my_user_info", {}),
    ("get_my_preferences", {}),
    ("get_asset_statistics", {}),
    ("get_album_statistics", {}),
    ("get_memory_statistics", {}),
    ("search_explore", {}),
    ("search_cities", {}),
    ("empty_trash", {}),
    ("restore_trash", {}),
]

async def main():
    print(f"# Test Report — Immich MCP Server")
    print(f"\n**Date**: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    print(f"**Server**: {MCP_URL}")
    print(f"**Run ID**: {rid}")
    print()

    async with MCPSession(MCP_URL, MCP_HEADERS) as session:
        # Phase 0: Session Init & Tool Discovery
        log("\n=== Phase 0: Session Init & Tool Discovery ===")
        tools_list = await session.list_tools()
        tool_names = [t["name"] for t in tools_list]
        print(f"**Discovered**: {len(tool_names)} tools")
        log(f"Tools: {', '.join(sorted(tool_names))}")

        # Get real asset IDs from the server for asset-dependent tools
        log("Fetching existing assets...")
        global ASSET_IDS
        import httpx as _httpx
        ASSET_IDS = []
        try:
            r = _httpx.post("http://localhost:2283/api/search/metadata",
                headers={"x-api-key": API_KEY},
                json={"page": 1, "size": 50})
            data = r.json()
            items = data.get("assets", {}).get("items", [])
            ASSET_IDS = [item["id"] for item in items if item.get("id")]
            log(f"Found {len(ASSET_IDS)} assets: {ASSET_IDS[:3]}...")
        except Exception as e:
            log(f"WARNING: Could not fetch assets: {e}")
        if not ASSET_IDS:
            log("WARNING: No assets found — asset-dependent tests will use FAKE_UUID")
            ASSET_IDS = [FAKE_UUID]
        if ASSET_IDS:
            log(f"Uploaded {len(ASSET_IDS)} assets: {ASSET_IDS}")
        else:
            log("WARNING: No assets uploaded — asset-dependent tests will use FAKE_UUID")
            ASSET_IDS = [FAKE_UUID]

        # Phase 1: Domain-Specific Tests (parameterless + simple tools)
        log("\n=== Phase 1: Domain-Specific Tests ===")
        store_keys_map = {"get_my_user_info": "get_my_user_info", "get_all_users": "get_all_users"}
        phase1_idx = 1
        for tool_name, tool_params in DOMAIN_TESTS:
            sk = store_keys_map.get(tool_name)
            if sk:
                await run_test_with_store(
                    session, f"A{phase1_idx} {tool_name}", tool_name, tool_params,
                    store_key=sk
                )
            else:
                await run_test(
                    session, f"A{phase1_idx} {tool_name}", tool_name, tool_params
                )
            phase1_idx += 1

        # Phase 2: List Tools (get_all for each resource + extras)
        log("\n=== Phase 2: List Tools ===")
        for entry in RESOURCE_TESTS:
            label = entry[0]
            list_tool_name = entry[3]
            await run_test(session, f"B2 list_{label.lower()}", list_tool_name)
        await run_test(session, "B2 list_library", "get_all_libraries", {})
        await run_test(session, "B2 list_memory", "get_all_memories", {})
        await run_test(session, "B2 list_stack", "get_all_stacks", {})
        await run_test(session, "B2 list_sharedlink", "get_all_shared_links", {})
        await run_test(session, "B2 list_partner", "get_all_partners", {"direction": "shared-by"})
        await run_test(session, "B2 list_duplicate", "get_all_duplicates", {})

        # Phase 3: CRUD Cycle for Album, Tag, Person
        log("\n=== Phase 3: Resource CRUD Cycle ===")
        for entry in RESOURCE_TESTS:
            label, create_tool, create_params, _, get_tool, update_tool, \
                update_params, delete_tool = entry
            key = label.lower()

            await run_test_with_store(
                session, f"C1 create_{key}", create_tool, create_params,
                store_key=f"create_{key}"
            )
            cid = pick_id(f"create_{key}")

            await run_test_with_store(
                session, f"C2 get_{key}_by_id", get_tool,
                {"id": cid} if cid else {"id": FAKE_UUID}, store_key=f"get_{key}"
            )

            gid = pick_id(f"get_{key}") or cid

            upd = dict(update_params)
            upd["id"] = gid if gid else FAKE_UUID
            await run_test(
                session, f"C3 update_{key}", update_tool, upd
            )

            await run_test(
                session, f"C4 delete_{key}_by_id", delete_tool,
                {"id": gid} if gid else {"id": FAKE_UUID}
            )

            await run_verify_delete(
                session, f"C5 verify_delete_{key}", get_tool,
                {"id": gid} if gid else {"id": FAKE_UUID}
            )

        # Phase 3b: Library CRUD (needs ownerId from get_my_user_info)
        log("\n=== Phase 3b: Library CRUD ===")
        await run_test_with_store(
            session, "C1b fetch_my_user", "get_my_user_info", {},
            store_key="my_user_info"
        )
        owner_id = pick_id("my_user_info") or FAKE_UUID
        await run_test_with_store(
            session, "C1b create_library", "create_library",
            {"name": make_name("Library"), "ownerId": owner_id},
            store_key="create_library"
        )
        lib_id = pick_id("create_library") or FAKE_UUID
        await run_test_with_store(
            session, "C2b get_library_by_id", "get_library_by_id",
            {"id": lib_id}, store_key="get_library"
        )
        gid = pick_id("get_library") or lib_id
        await run_test(
            session, "C3b update_library", "update_library",
            {"id": gid, "name": make_name("LibUpdated")}
        )
        await run_test(
            session, "C4b delete_library_by_id", "delete_library_by_id",
            {"id": gid}
        )
        await run_verify_delete(
            session, "C5b verify_delete_library", "get_library_by_id",
            {"id": gid}
        )

        # Phase 3c: Memory CRUD
        log("\n=== Phase 3c: Memory CRUD ===")
        await run_test_with_store(
            session, "C1c create_memory", "create_memory",
            {"type": "on_this_day", "data": json.dumps({"year": 2026}),
             "memoryAt": "2026-06-22T15:00:00+00:00"},
            store_key="create_memory"
        )
        mem_id = pick_id("create_memory") or FAKE_UUID
        await run_test_with_store(
            session, "C2c get_memory_by_id", "get_memory_by_id",
            {"id": mem_id}, store_key="get_memory"
        )
        gid = pick_id("get_memory") or mem_id
        await run_test(
            session, "C3c update_memory", "update_memory",
            {"id": gid, "isSaved": True}
        )
        await run_test(
            session, "C4c delete_memory_by_id", "delete_memory_by_id",
            {"id": gid}
        )
        await run_verify_delete(
            session, "C5c verify_delete_memory", "get_memory_by_id",
            {"id": gid}
        )

        # Phase 3d: Stack CRUD (requires 2+ asset IDs — backend constraint)
        log("\n=== Phase 3d: Stack CRUD ===")
        a_ids = ASSET_IDS[:2]
        await run_test_with_store(
            session, "C1d create_stack", "create_stack",
            {"assetIds": f"{a_ids[0]},{a_ids[1]}"},
            store_key="create_stack"
        )
        stack_id = pick_id("create_stack") or FAKE_UUID
        await run_test_with_store(
            session, "C2d get_stack_by_id", "get_stack_by_id",
            {"id": stack_id}, store_key="get_stack"
        )
        gid = pick_id("get_stack") or stack_id
        await run_test(
            session, "C3d update_stack", "update_stack",
            {"id": gid, "primaryAssetId": ASSET_IDS[0]}
        )
        await run_test(
            session, "C4d delete_stack_by_id", "delete_stack_by_id",
            {"id": gid}
        )
        await run_verify_delete(
            session, "C5d verify_delete_stack", "get_stack_by_id",
            {"id": gid}
        )

        # Phase 3e: SharedLink CRUD (use INDIVIDUAL with real asset)
        log("\n=== Phase 3e: SharedLink CRUD ===")
        await run_test_with_store(
            session, "C1e create_shared_link", "create_shared_link",
            {"type": "INDIVIDUAL", "assetIds": ASSET_IDS[0]},
            store_key="create_shared_link"
        )
        sl_id = pick_id("create_shared_link") or FAKE_UUID
        await run_test_with_store(
            session, "C2e get_shared_link_by_id", "get_shared_link_by_id",
            {"id": sl_id}, store_key="get_shared_link"
        )
        gid = pick_id("get_shared_link") or sl_id
        await run_test(
            session, "C3e update_shared_link", "update_shared_link",
            {"id": gid, "description": "Updated"}
        )
        await run_test(
            session, "C4e delete_shared_link_by_id", "delete_shared_link_by_id",
            {"id": gid}
        )
        await run_verify_delete(
            session, "C5e verify_delete_shared_link", "get_shared_link_by_id",
            {"id": gid}
        )

        # Phase 3f: Partner Operations (non-standard CRUD)
        log("\n=== Phase 3f: Partner Operations ===")
        second_user_id = owner_id
        users_data = store.get("get_all_users", {})
        if isinstance(users_data, dict):
            items = get_list_items(users_data)
            for u in items:
                uid = u.get("id", "")
                if uid and uid != owner_id:
                    second_user_id = uid
                    break
        await run_test(
            session, "C1f create_partner", "create_partner",
            {"sharedWithId": owner_id}
        )
        await run_test_with_store(
            session, "C2f get_all_partners", "get_all_partners",
            {"direction": "shared-by"}, store_key="get_partner"
        )
        partner_id = pick_id("get_partner") or owner_id
        partner_user = partner_id if partner_id and partner_id != FAKE_UUID else owner_id
        await run_test(
            session, "C3f update_partner", "update_partner",
            {"id": partner_id, "inTimeline": True}
        )
        await run_test(
            session, "C4f delete_partner_by_id", "delete_partner_by_id",
            {"id": partner_id}
        )

        # Phase 4: Activity Tools
        log("\n=== Phase 4: Activity Tools ===")
        act_album_name = make_name("ActAlbum")
        await run_test_with_store(
            session, "D1 create_activity_album", "create_album",
            {"albumName": act_album_name}, store_key="create_activity_album"
        )
        act_album_id = pick_id("create_activity_album") or FAKE_UUID
        await run_test(
            session, "D2 get_all_activities", "get_all_activities",
            {"albumId": act_album_id}
        )
        await run_test(
            session, "D3 get_activity_statistics", "get_activity_statistics",
            {"albumId": act_album_id}
        )
        await run_test_with_store(
            session, "D4 create_activity", "create_activity",
            {"albumId": act_album_id, "type": "comment", "comment": "Test comment"},
            store_key="created_activity")
        act_id = pick_id("created_activity") or ASSET_IDS[0]
        await run_test(
            session, "N1 delete_activity_by_id", "delete_activity_by_id",
            {"id": act_id}
        )
        # Keep album alive — it will be used in Phase 5, deleted at end of Phase 5

        # Phase 5: Album Relationship Tools (use album from Phase 4)
        log("\n=== Phase 5: Album Relationship Tools ===")
        second_uid = second_user_id if second_user_id != owner_id else owner_id
        await run_test(
            session, "E1 get_album_map_markers", "get_album_map_markers",
            {"id": act_album_id}
        )
        await run_test(
            session, "E2 add_assets_to_album", "add_assets_to_album",
            {"id": act_album_id, "assetIds": ASSET_IDS[0]}
        )
        await run_test(
            session, "E3 remove_assets_from_album", "remove_assets_from_album",
            {"id": act_album_id, "assetIds": ASSET_IDS[0]}
        )
        await run_test(
            session, "E4 share_album_with_users", "share_album_with_users",
            {"id": act_album_id, "albumUsers": second_uid}
        )
        await run_test(
            session, "E5 remove_user_from_album", "remove_user_from_album",
            {"id": act_album_id, "userId": second_uid}
        )
        # Now clean up activity album
        await run_test(
            session, "D5 delete_activity_album", "delete_album_by_id",
            {"id": act_album_id}
        )

        # Phase 6: Tag Relationship Tools
        log("\n=== Phase 6: Tag Relationship Tools ===")
        # Create a fresh tag for relationship tests
        await run_test_with_store(
            session, "F0 create_rel_tag", "create_tag",
            {"name": make_name("RelTag")}, store_key="create_rel_tag"
        )
        rel_tag_id = pick_id("create_rel_tag") or ASSET_IDS[0]
        await run_test(
            session, "F1 upsert_tags", "upsert_tags",
            {"tags": make_name("UpsertTag")}
        )
        await run_test(
            session, "F2 tag_assets", "tag_assets",
            {"tagIds": rel_tag_id, "assetIds": ASSET_IDS[0]}
        )
        await run_test(
            session, "F3 tag_assets_by_tag", "tag_assets_by_tag",
            {"id": rel_tag_id, "assetIds": ASSET_IDS[0]}
        )
        await run_test(
            session, "F4 untag_assets", "untag_assets",
            {"id": rel_tag_id, "assetIds": ASSET_IDS[0]}
        )

        # Phase 7: Person Relationship Tools
        log("\n=== Phase 7: Person Relationship Tools ===")
        # Create a fresh person for relationship tests
        await run_test_with_store(
            session, "F0 create_rel_person", "create_person",
            {"name": make_name("RelPerson")}, store_key="create_rel_person"
        )
        rel_person_id = pick_id("create_rel_person") or ASSET_IDS[0]
        await run_test(
            session, "G1 get_person_statistics", "get_person_statistics",
            {"id": rel_person_id}
        )
        await run_test(
            session, "G2 get_person_thumbnail_url", "get_person_thumbnail_url",
            {"id": rel_person_id}
        )
        await run_test(
            session, "G3 merge_people", "merge_people",
            {"id": rel_person_id, "mergeIds": ASSET_IDS[0]}
        )

        # Phase 8: Library Relationship Tools
        log("\n=== Phase 8: Library Relationship Tools ===")
        # Create a fresh library for relationship tests
        my_info = store.get("my_user_info", {})
        my_oid = my_info.get("id", "") if isinstance(my_info, dict) else ""
        await run_test_with_store(
            session, "F0 create_rel_library", "create_library",
            {"name": make_name("RelLibrary"), "ownerId": my_oid or owner_id},
            store_key="create_rel_library"
        )
        rel_lib_id = pick_id("create_rel_library") or ASSET_IDS[0]
        await run_test(
            session, "H1 scan_library", "scan_library",
            {"id": rel_lib_id}
        )
        await run_test(
            session, "H2 get_library_statistics", "get_library_statistics",
            {"id": rel_lib_id}
        )


        # Phase 9: Memory Relationship Tools
        log("\n=== Phase 9: Memory Relationship Tools ===")
        await run_test_with_store(
            session, "I0 create_fresh_memory", "create_memory",
            {"type": "on_this_day", "data": json.dumps({"year": 2026}),
             "memoryAt": "2026-06-22T15:00:00+00:00"},
            store_key="fresh_memory"
        )
        fresh_mem_id = pick_id("fresh_memory") or FAKE_UUID
        await run_test(
            session, "I1 add_assets_to_memory", "add_assets_to_memory",
            {"id": fresh_mem_id, "assetIds": ASSET_IDS[0]}
        )

        # Phase 10: Stack Relationship Tools
        log("\n=== Phase 10: Stack Relationship Tools ===")
        a_ids = ASSET_IDS[:2]
        await run_test_with_store(
            session, "J0 create_fresh_stack", "create_stack",
            {"assetIds": f"{a_ids[0]},{a_ids[1]}"},
            store_key="fresh_stack"
        )
        fresh_stack_id = pick_id("fresh_stack") or FAKE_UUID
        await run_test(
            session, "J1 remove_asset_from_stack", "remove_asset_from_stack",
            {"id": fresh_stack_id, "assetId": ASSET_IDS[1] if len(ASSET_IDS) > 1 else ASSET_IDS[0]}
        )

        # Phase 11: Asset-Dependent Tools
        log("\n=== Phase 11: Asset-Dependent Tools ===")
        _aid = ASSET_IDS[0]
        await run_test(
            session, "K1 get_asset_thumbnail_url", "get_asset_thumbnail_url",
            {"id": _aid}
        )
        await run_test(
            session, "K2 get_asset_original_url", "get_asset_original_url",
            {"id": _aid}
        )
        await run_test(
            session, "K3 get_asset_by_id", "get_asset_by_id",
            {"id": _aid}
        )
        await run_test(
            session, "K4 get_asset_ocr", "get_asset_ocr",
            {"id": _aid}
        )
        await run_test(
            session, "K5 get_asset_metadata", "get_asset_metadata",
            {"id": _aid}
        )
        await run_test(
            session, "K7 get_asset_edits", "get_asset_edits",
            {"id": _aid}
        )
        await run_test(
            session, "K8 update_asset", "update_asset",
            {"id": _aid, "isFavorite": True}
        )
        await run_test(
            session, "K9 update_asset_edits", "update_asset_edits",
            {"id": _aid, "edits": json.dumps([{"action": "rotate", "parameters": {"angle": 90}}])}
        )
        await run_test(
            session, "K10 update_asset_metadata", "update_asset_metadata",
            {"id": _aid, "metadata": json.dumps({"ExifIFD:DateTimeOriginal": "2026:01:01 12:00:00"})}
        )
        await run_test(
            session, "K6 get_asset_metadata_by_key", "get_asset_metadata_by_key",
            {"id": _aid, "key": "ExifIFD:DateTimeOriginal"}
        )
        await run_test(
            session, "K11 delete_assets", "delete_assets",
            {"ids": _aid, "force": False}
        )
        await run_test(
            session, "K12 bulk_update_assets", "bulk_update_assets",
            {"ids": _aid, "isFavorite": False}
        )
        await run_test(
            session, "K13 copy_asset", "copy_asset",
            {"sourceId": _aid, "targetId": ASSET_IDS[1] if len(ASSET_IDS) > 1 else _aid}
        )

        # Phase 12: Face Tools
        log("\n=== Phase 12: Face Tools ===")
        # Use an asset that has detected faces (e.g. one of the Trump images)
        face_asset_id = ASSET_IDS[1] if len(ASSET_IDS) > 1 else _aid
        # ML microservices aren't running, so faces aren't auto-detected.
        # Create a face manually so L1-L3 have data to work with.
        if rel_person_id and rel_person_id != _aid:
            try:
                import httpx as _httpx_face
                _httpx_face.post("http://localhost:2283/api/faces",
                    headers={"x-api-key": API_KEY},
                    json={"assetId": face_asset_id, "personId": rel_person_id,
                          "x": 50, "y": 50, "width": 100, "height": 150,
                          "imageWidth": 500, "imageHeight": 282})
            except Exception:
                pass
        await run_test_with_store(
            session, "L1 get_faces_by_asset", "get_faces_by_asset",
            {"id": face_asset_id}, store_key="faces_by_asset"
        )
        face_id = pick_first_face_id("faces_by_asset") or face_asset_id
        await run_test(
            session, "L2 reassign_face", "reassign_face",
            {"assetId": face_asset_id, "personId": rel_person_id}
        )
        await run_test(
            session, "L3 delete_face", "delete_face",
            {"id": face_id, "force": True}
        )

        # Phase 13: Duplicate Tools
        log("\n=== Phase 13: Duplicate Tools ===")
        await run_test(
            session, "M2 dismiss_duplicate_group", "dismiss_duplicate_group",
            {"id": _aid}
        )

        # Phase 14: (empty - N1 moved to Phase 4)

        # Phase 15: Server & System Tools
        log("\n=== Phase 15: Server & System Tools ===")
        await run_test(
            session, "O1 get_time_bucket", "get_time_bucket",
            {"size": "MONTH", "timeBucket": "2026-06-01"}
        )

        # Phase 16: User & Account Tools
        log("\n=== Phase 16: User & Account Tools ===")
        my_info = store.get("my_user_info", {})
        my_id = my_info.get("id", "") if isinstance(my_info, dict) else FAKE_UUID
        await run_test(
            session, "P1 get_user_by_id", "get_user_by_id",
            {"id": my_id}
        )
        await run_test(
            session, "P2 update_my_user", "update_my_user",
            {"name": make_name("UpdatedUser")}
        )
        await run_test(
            session, "P3 update_my_preferences", "update_my_preferences",
            {"preferences": json.dumps({"language": "en"})}
        )
        await run_test(
            session, "P4 get_user_profile_image_url", "get_user_profile_image_url",
            {"id": my_id}
        )

        # Phase 17: Trash Tools
        log("\n=== Phase 17: Trash Tools ===")
        await run_test(
            session, "Q1 restore_trash_assets", "restore_trash_assets",
            {"ids": _aid}
        )

        # Phase 18: Search Tools
        log("\n=== Phase 18: Search Tools ===")
        search_params = {"query": "test", "page": 1, "size": 10}
        await run_test(
            session, "R1 search_metadata", "search_metadata", search_params
        )
        await run_test(
            session, "R2 search_smart", "search_smart",
            {"query": "test"}
        )

        # Report Summary
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
