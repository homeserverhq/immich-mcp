import os
import re
import datetime as dt
from typing import Any, Optional

import httpx


def _normalize_datetime(value: str) -> str:
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$', value):
        parsed = dt.datetime.fromisoformat(value)
        parsed = parsed.astimezone(dt.timezone.utc)
        return parsed.strftime('%Y-%m-%d %H:%M:%S')
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value):
        raise ValueError(
            f"Invalid datetime: {value}. Timezone offset is required. "
            "Must use format: 2026-06-22T15:00:00-04:00"
        )
    return value


COMMON_FIELDS = {
    "asset": {"id", "type", "originalFileName", "originalMimeType", "fileCreatedAt",
              "isFavorite", "isArchived", "isTrashed", "ownerId", "libraryId",
              "thumbhash", "resized", "hasMetadata", "localDateTime", "originalPath"},
    "album": {"id", "albumName", "description", "assetCount", "ownerId",
              "createdAt", "updatedAt", "shared", "hasSharedLink",
              "isActivityEnabled", "albumThumbnailAssetId", "order"},
    "tag": {"id", "name", "value", "color", "parentId", "createdAt", "updatedAt"},
    "person": {"id", "name", "thumbnailPath", "isFavorite", "isHidden", "color", "updatedAt"},
    "library": {"id", "name", "ownerId", "assetCount", "importPaths", "exclusionPatterns",
                "createdAt", "updatedAt", "refreshedAt"},
    "memory": {"id", "type", "isSaved", "memoryAt", "ownerId", "createdAt",
               "seenAt", "showAt", "hideAt", "deletedAt"},
    "stack": {"id", "primaryAssetId", "assets"},
    "shared_link": {"id", "type", "userId", "description", "allowDownload", "allowUpload",
                    "showMetadata", "createdAt", "expiresAt", "slug"},
    "activity": {"id", "type", "userId", "assetId", "albumId", "comment", "createdAt"},
    "partner": {"id", "name", "email", "avatarColor", "inTimeline"},
    "user": {"id", "name", "email", "avatarColor", "profileImagePath", "profileChangedAt"},
    "duplicate": {"id", "assetIds", "assets"},
    "queue": {"name", "queueStatus", "jobCounts"},
}


def _filter_fields(data: Any, common_set: set[str]) -> Any:
    """Filter dict or list of dicts to only include common fields."""
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in common_set}
    if isinstance(data, list):
        return [_filter_fields(item, common_set) for item in data]
    return data


class ImmichClient:
    """Client for Immich API with auth passthrough."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or os.getenv("IMMICH_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError(
                "Immich URL required. Set IMMICH_BASE_URL env var "
                "or pass base_url."
            )
        public_url = os.getenv("IMMICH_PUBLIC_URL", "").rstrip("/")
        self.public_url = public_url or self.base_url

    def _get_headers(self, api_key: Optional[str] = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    async def request(
        self,
        method: str,
        path: str,
        api_key: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        url = f"{self.base_url}/api{path}"
        headers = self._get_headers(api_key)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            ct = response.headers.get("content-type", "")
            if ct.startswith("application/json"):
                return response.json()
            return {"text": response.text}

    async def get(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("GET", path, api_key, **kwargs)

    async def post(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("POST", path, api_key, **kwargs)

    async def put(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("PUT", path, api_key, **kwargs)

    async def patch(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("PATCH", path, api_key, **kwargs)

    async def delete(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("DELETE", path, api_key, **kwargs)

    # ==========================================================================
    # Server Domain
    # ==========================================================================

    async def get_server_ping(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/ping", api_key)

    async def get_server_version(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/version", api_key)

    async def get_server_about(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/about", api_key)

    async def get_server_config(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/config", api_key)

    async def get_server_features(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/features", api_key)

    async def get_server_statistics(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/statistics", api_key)

    async def get_server_storage(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/storage", api_key)

    async def get_server_media_types(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/media-types", api_key)

    async def get_server_version_check(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/version-check", api_key)

    async def get_server_version_history(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/version-history", api_key)

    async def get_server_apk_links(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/server/apk-links", api_key)

    # ==========================================================================
    # Asset Domain
    # ==========================================================================

    async def get_asset_by_id(
        self, asset_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/assets/{asset_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["asset"])
        return data

    async def get_asset_statistics(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/assets/statistics", api_key)

    async def get_asset_ocr(self, asset_id: str, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/assets/{asset_id}/ocr", api_key)

    async def get_asset_metadata(self, asset_id: str, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/assets/{asset_id}/metadata", api_key)

    async def get_asset_metadata_by_key(self, asset_id: str, key: str, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/assets/{asset_id}/metadata/{key}", api_key)

    async def get_asset_edits(self, asset_id: str, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/assets/{asset_id}/edits", api_key)

    async def get_asset_thumbnail_url(self, asset_id: str, api_key: Optional[str] = None) -> str:
        return f"{self.public_url}/assets/{asset_id}/thumbnail"

    async def get_asset_original_url(self, asset_id: str, api_key: Optional[str] = None) -> str:
        return f"{self.public_url}/assets/{asset_id}/original"

    async def update_asset(self, asset_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/assets/{asset_id}", api_key, json=payload)

    async def update_asset_edits(self, asset_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/assets/{asset_id}/edits", api_key, json=payload)

    async def update_asset_metadata(self, asset_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/assets/{asset_id}/metadata", api_key, json=payload)

    async def delete_asset_metadata_by_key(self, asset_id: str, key: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/assets/{asset_id}/metadata/{key}", api_key)

    async def delete_assets(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete("/assets", api_key, json=payload)

    async def bulk_update_assets(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put("/assets", api_key, json=payload)

    async def copy_asset(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put("/assets/copy", api_key, json=payload)

    async def check_bulk_upload(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/assets/bulk-upload-check", api_key, json=payload)

    async def run_asset_jobs(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/assets/jobs", api_key, json=payload)

    async def delete_asset_edits(self, asset_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/assets/{asset_id}/edits", api_key)

    async def get_asset_video_playback(self, asset_id: str, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/assets/{asset_id}/video/playback", api_key)

    # ==========================================================================
    # Album Domain
    # ==========================================================================

    async def get_all_albums(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
        params: Optional[dict] = None,
    ) -> Any:
        data = await self.get("/albums", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["album"])
        return data

    async def get_album_by_id(
        self, album_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/albums/{album_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["album"])
        return data

    async def create_album(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/albums", api_key, json=payload)

    async def update_album(self, album_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.patch(f"/albums/{album_id}", api_key, json=payload)

    async def delete_album_by_id(self, album_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/albums/{album_id}", api_key)

    async def add_assets_to_album(self, album_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/albums/{album_id}/assets", api_key, json=payload)

    async def remove_assets_from_album(self, album_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/albums/{album_id}/assets", api_key, json=payload)

    async def add_users_to_album(self, album_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/albums/{album_id}/users", api_key, json=payload)

    async def update_user_role_in_album(self, album_id: str, user_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/albums/{album_id}/user/{user_id}", api_key, json=payload)

    async def remove_user_from_album(self, album_id: str, user_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/albums/{album_id}/user/{user_id}", api_key)

    async def get_album_statistics(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/albums/statistics", api_key)

    async def get_album_map_markers(self, album_id: str, api_key: Optional[str] = None) -> Any:
        try:
            return await self.get(f"/albums/{album_id}/map-markers", api_key)
        except Exception:
            return await self.get("/map/markers", api_key, params={"albumId": album_id})

    async def add_assets_to_albums(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put("/albums/assets", api_key, json=payload)

    # ==========================================================================
    # Tag Domain
    # ==========================================================================

    async def get_all_tags(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/tags", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

    async def get_tag_by_id(
        self, tag_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/tags/{tag_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

    async def create_tag(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/tags", api_key, json=payload)

    async def update_tag(self, tag_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/tags/{tag_id}", api_key, json=payload)

    async def delete_tag_by_id(self, tag_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/tags/{tag_id}", api_key)

    async def upsert_tags(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put("/tags", api_key, json=payload)

    async def tag_assets(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put("/tags/assets", api_key, json=payload)

    async def tag_assets_by_tag(self, tag_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/tags/{tag_id}/assets", api_key, json=payload)

    async def untag_assets(self, tag_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/tags/{tag_id}/assets", api_key, json=payload)

    # ==========================================================================
    # People / Faces Domain
    # ==========================================================================

    async def get_all_people(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/people", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["person"])
        return data

    async def get_person_by_id(
        self, person_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/people/{person_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["person"])
        return data

    async def create_person(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/people", api_key, json=payload)

    async def update_person(self, person_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/people/{person_id}", api_key, json=payload)

    async def delete_person_by_id(self, person_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/people/{person_id}", api_key)

    async def bulk_update_people(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put("/people", api_key, json=payload)

    async def bulk_delete_people(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete("/people", api_key, json=payload)

    async def merge_people(self, person_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/people/{person_id}/merge", api_key, json=payload)

    async def reassign_faces(self, person_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/people/{person_id}/reassign", api_key, json=payload)

    async def get_person_statistics(self, person_id: str, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/people/{person_id}/statistics", api_key)

    async def get_person_thumbnail_url(self, person_id: str, api_key: Optional[str] = None) -> str:
        return f"{self.public_url}/people/{person_id}/thumbnail"

    async def get_faces_by_asset(self, asset_id: str, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/faces?id={asset_id}", api_key)

    async def create_face(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/faces", api_key, json=payload)

    async def delete_face(self, face_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.request("DELETE", f"/faces/{face_id}", api_key, json=payload)

    # ==========================================================================
    # Library Domain
    # ==========================================================================

    async def get_all_libraries(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/libraries", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["library"])
        return data

    async def get_library_by_id(
        self, library_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/libraries/{library_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["library"])
        return data

    async def create_library(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/libraries", api_key, json=payload)

    async def update_library(self, library_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/libraries/{library_id}", api_key, json=payload)

    async def delete_library_by_id(self, library_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/libraries/{library_id}", api_key)

    async def scan_library(self, library_id: str, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/libraries/{library_id}/scan", api_key)

    async def validate_library(self, library_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/libraries/{library_id}/validate", api_key, json=payload)

    async def get_library_statistics(self, library_id: str, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/libraries/{library_id}/statistics", api_key)

    # ==========================================================================
    # Memory Domain
    # ==========================================================================

    async def get_all_memories(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/memories", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["memory"])
        return data

    async def get_memory_by_id(
        self, memory_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/memories/{memory_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["memory"])
        return data

    async def create_memory(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/memories", api_key, json=payload)

    async def update_memory(self, memory_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/memories/{memory_id}", api_key, json=payload)

    async def delete_memory_by_id(self, memory_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/memories/{memory_id}", api_key)

    async def add_assets_to_memory(self, memory_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/memories/{memory_id}/assets", api_key, json=payload)

    async def remove_assets_from_memory(self, memory_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/memories/{memory_id}/assets", api_key, json=payload)

    async def get_memory_statistics(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/memories/statistics", api_key)

    # ==========================================================================
    # Stack Domain
    # ==========================================================================

    async def get_all_stacks(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/stacks", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["stack"])
        return data

    async def get_stack_by_id(
        self, stack_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/stacks/{stack_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["stack"])
        return data

    async def create_stack(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/stacks", api_key, json=payload)

    async def update_stack(self, stack_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/stacks/{stack_id}", api_key, json=payload)

    async def delete_stack_by_id(self, stack_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/stacks/{stack_id}", api_key)

    async def delete_stacks(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete("/stacks", api_key, json=payload)

    async def remove_asset_from_stack(self, stack_id: str, asset_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/stacks/{stack_id}/assets/{asset_id}", api_key)

    # ==========================================================================
    # Shared Link Domain
    # ==========================================================================

    async def get_all_shared_links(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/shared-links", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["shared_link"])
        return data

    async def get_shared_link_by_id(
        self, shared_link_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/shared-links/{shared_link_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["shared_link"])
        return data

    async def get_current_shared_link(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/shared-links/me", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["shared_link"])
        return data

    async def create_shared_link(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/shared-links", api_key, json=payload)

    async def update_shared_link(self, shared_link_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.patch(f"/shared-links/{shared_link_id}", api_key, json=payload)

    async def delete_shared_link_by_id(self, shared_link_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/shared-links/{shared_link_id}", api_key)

    async def add_assets_to_shared_link(self, shared_link_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/shared-links/{shared_link_id}/assets", api_key, json=payload)

    async def remove_assets_from_shared_link(self, shared_link_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/shared-links/{shared_link_id}/assets", api_key, json=payload)

    # ==========================================================================
    # Activity Domain
    # ==========================================================================

    async def get_all_activities(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
        params: Optional[dict] = None,
    ) -> Any:
        data = await self.get("/activities", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["activity"])
        return data

    async def get_activity_statistics(self, api_key: Optional[str] = None, params: Optional[dict] = None) -> Any:
        return await self.get("/activities/statistics", api_key, params=params)

    async def create_activity(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/activities", api_key, json=payload)

    async def delete_activity_by_id(self, activity_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/activities/{activity_id}", api_key)

    # ==========================================================================
    # Partner Domain
    # ==========================================================================

    async def get_all_partners(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
        params: Optional[dict] = None,
    ) -> Any:
        data = await self.get("/partners", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["partner"])
        return data

    async def create_partner(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/partners", api_key, json=payload)

    async def update_partner(self, partner_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/partners/{partner_id}", api_key, json=payload)

    async def delete_partner_by_id(self, partner_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/partners/{partner_id}", api_key)

    # ==========================================================================
    # Search Domain
    # ==========================================================================

    async def search_metadata(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/search/metadata", api_key, json=payload)

    async def search_smart(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/search/smart", api_key, json=payload)

    async def search_random(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/search/random", api_key, json=payload)

    async def search_suggestions(self, params: dict, api_key: Optional[str] = None) -> Any:
        return await self.get("/search/suggestions", api_key, params=params)

    async def search_explore(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/search/explore", api_key)

    async def search_cities(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/search/cities", api_key)

    async def search_person(self, params: dict, api_key: Optional[str] = None) -> Any:
        return await self.get("/search/person", api_key, params=params)

    async def search_places(self, params: dict, api_key: Optional[str] = None) -> Any:
        return await self.get("/search/places", api_key, params=params)

    async def search_statistics(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/search/statistics", api_key, json=payload)

    # ==========================================================================
    # Timeline & Map Domain
    # ==========================================================================

    async def get_time_buckets(self, params: dict, api_key: Optional[str] = None) -> Any:
        return await self.get("/timeline/buckets", api_key, params=params)

    async def get_time_bucket(self, params: dict, api_key: Optional[str] = None) -> Any:
        return await self.get("/timeline/bucket", api_key, params=params)

    async def get_map_markers(self, params: dict, api_key: Optional[str] = None) -> Any:
        return await self.get("/map/markers", api_key, params=params)

    async def reverse_geocode(self, params: dict, api_key: Optional[str] = None) -> Any:
        return await self.get("/map/reverse-geocode", api_key, params=params)

    # ==========================================================================
    # Duplicates Domain
    # ==========================================================================

    async def get_all_duplicates(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/duplicates", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["duplicate"])
        return data

    async def dismiss_duplicate_group(self, duplicate_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/duplicates/{duplicate_id}", api_key)

    async def delete_duplicates(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete("/duplicates", api_key, json=payload)

    # ==========================================================================
    # Trash Domain
    # ==========================================================================

    async def empty_trash(self, api_key: Optional[str] = None) -> Any:
        return await self.post("/trash/empty", api_key)

    async def restore_trash(self, api_key: Optional[str] = None) -> Any:
        return await self.post("/trash/restore", api_key)

    async def restore_trash_assets(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/trash/restore/assets", api_key, json=payload)

    # ==========================================================================
    # System Config Domain
    # ==========================================================================

    async def get_system_config(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/system-config", api_key)

    async def get_system_config_defaults(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/system-config/defaults", api_key)

    async def get_storage_template_options(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/system-config/storage-template-options", api_key)

    # ==========================================================================
    # User Domain
    # ==========================================================================

    async def get_all_users(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/users", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["user"])
        return data

    async def get_user_by_id(
        self, user_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/users/{user_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["user"])
        return data

    async def get_my_user_info(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/users/me", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["user"])
        return data

    async def update_my_user(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put("/users/me", api_key, json=payload)

    async def get_my_preferences(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/users/me/preferences", api_key)

    async def update_my_preferences(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put("/users/me/preferences", api_key, json=payload)

    async def set_my_license(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put("/users/me/license", api_key, json=payload)

    async def delete_my_license(self, api_key: Optional[str] = None) -> Any:
        return await self.delete("/users/me/license", api_key)

    async def get_my_onboarding(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/users/me/onboarding", api_key)

    async def update_my_onboarding(self, api_key: Optional[str] = None) -> Any:
        return await self.put("/users/me/onboarding", api_key)

    async def delete_my_onboarding(self, api_key: Optional[str] = None) -> Any:
        return await self.delete("/users/me/onboarding", api_key)

    async def get_user_profile_image_url(self, user_id: str, api_key: Optional[str] = None) -> str:
        return f"{self.public_url}/users/{user_id}/profile-image"

    async def delete_profile_image(self, api_key: Optional[str] = None) -> Any:
        return await self.delete("/users/profile-image", api_key)
