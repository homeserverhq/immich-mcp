import base64
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
              "ownerId", "isFavorite"},
    "album": {"id", "albumName", "description", "assetCount", "ownerId", "createdAt"},
    "tag": {"id", "name", "value", "color", "parentId"},
    "person": {"id", "name", "color"},
    "library": {"id", "name", "ownerId", "assetCount", "importPaths"},
    "memory": {"id", "type", "memoryAt", "ownerId"},
    "stack": {"id", "primaryAssetId", "assets"},
    "shared_link": {"id", "type", "userId", "description", "allowDownload", "allowUpload", "slug", "key"},
    "activity": {"id", "type", "userId", "assetId", "albumId", "comment", "createdAt"},
    "partner": {"id", "name", "email", "inTimeline"},
    "user": {"id", "name", "email"},
    "duplicate": {"id", "assetIds", "assets"},
    "queue": {"name", "queueStatus", "jobCounts"},
    "server_ping": {"res"},
    "server_version": {"major", "minor", "patch"},
    "server_about": {"version", "name", "features"},
    "server_config": {"oauthButtonText", "isInitialized"},
    "server_features": {"smartSearch", "duplicateDetection", "reverseGeocoding",
                        "emailNotification", "socialFeatures", "facialRecognition"},
    "server_statistics": {"status", "startupTime", "usage", "licenseKey"},
    "server_storage": {"storageType", "diskSizeTotal", "diskSizeUsed", "diskSizeFree"},
    "server_media_types": {"image", "video", "sidecar"},
    "server_version_check": {"updateAvailable", "serverVersion", "releaseAsset"},
    "server_version_history": {"items"},
    "server_apk_links": {"items"},
    "system_config": {"config"},
    "system_config_defaults": {"config"},
    "storage_template": {"items"},
    "asset_statistics": {"count", "totalSizeBytes", "totalPixelSize",
                          "images", "videos", "other", "startDate", "endDate"},
    "asset_ocr": {"id", "assetId", "ocr"},
    "asset_metadata": {"items"},
    "asset_edits": {"items"},
    "album_statistics": {"albumCount", "assets"},
    "map_markers": {"count", "items"},
    "person_statistics": {"assets", "faces"},
    "faces": {"id", "personId", "assetId", "boundingBox"},
    "library_statistics": {"id", "name", "assetCount"},
    "memory_statistics": {"memoryCount", "assets"},
    "activity_statistics": {"count", "activities"},
    "search_suggestions": {"items"},
    "explore": {"items"},
    "cities": {"items"},
    "people": {"items"},
    "places": {"items"},
    "time_buckets": {"items"},
    "geocode": {"items"},
    "preferences": {"avatar"},
}


def _filter_fields(data: Any, common_set: set[str]) -> Any:
    """Filter dict or list of dicts to only include common fields."""
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in common_set}
    if isinstance(data, list):
        return [_filter_fields(item, common_set) for item in data]
    return data


# Public web URL routes for entity types that map to a per-item deep link.
# Format: entity -> (result field name, path template | None).
# A callable route takes the field dict and returns an absolute path (e.g. shared links).
_PUBLIC_ROUTES: dict[str, tuple[str, Any]] = {
    "asset": ("assetUrl", "/photos/{id}"),
    "album": ("albumUrl", "/albums/{id}"),
    "person": ("personUrl", "/people/{id}"),
    "partner": ("partnerUrl", "/partners/{id}"),
    "library": ("libraryUrl", "/admin/library-management/{id}"),
    "user": ("userUrl", "/admin/users/{id}"),
    "memory": ("memoryUrl", "/memory?id={id}"),
    # Shared links resolve to either the slug route (/s/{slug}) or key route (/share/{key}).
    "shared_link": ("sharedLinkUrl", None),
}


def _shared_link_path(obj: dict[str, Any]) -> Optional[str]:
    slug = obj.get("slug")
    if slug:
        return f"/s/{slug}"
    key = obj.get("key")
    if key:
        return f"/share/{key}"
    return None


def _build_public_path(entity: str, obj: dict[str, Any]) -> Optional[str]:
    """Build the web URL path for an entity field dict, or None if it can't be built."""
    if entity not in _PUBLIC_ROUTES:
        return None
    routes = _PUBLIC_ROUTES[entity]
    route = routes[1]
    if route is None:
        if entity == "shared_link":
            return _shared_link_path(obj)
        return None
    item_id = obj.get("id")
    if not item_id:
        return None
    return route.format(id=item_id)


def _augment_image_url(data: Any, entity: str, public_url: str) -> Any:
    """Inject the original-file URL (imageUrl) into each asset object."""
    if entity != "asset" or not public_url:
        return data
    if isinstance(data, list):
        for item in data:
            _augment_image_url(item, entity, public_url)
        return data
    if isinstance(data, dict):
        item_id = data.get("id")
        if item_id:
            data["imageUrl"] = f"{public_url}/api/assets/{item_id}/original"
    return data


def _augment_urls(data: Any, entity: str, public_url: str) -> Any:
    """Inject the public URL field ({entity}Url) into each entity object."""
    if not public_url or entity not in _PUBLIC_ROUTES:
        return data
    field_name = _PUBLIC_ROUTES[entity][0]
    if isinstance(data, list):
        for item in data:
            _augment_urls(item, entity, public_url)
            _augment_image_url(item, entity, public_url)
        return data
    if isinstance(data, dict):
        path = _build_public_path(entity, data)
        if path:
            data[f"{field_name}"] = f"{public_url}{path}"
        _augment_image_url(data, entity, public_url)
        return data
    return data


# Some list endpoints return the entity array wrapped in a plural key (e.g. people -> "people").
_PROCESS_WRAPPERS: dict[str, str] = {
    "person": "people",
}


def _process(data: Any, entity: str, include_all_fields: bool, public_url: str) -> Any:
    """Filter to common fields (unless full fields requested) and always augment the public URL."""
    wrapper = _PROCESS_WRAPPERS.get(entity)
    if wrapper and isinstance(data, dict) and isinstance(data.get(wrapper), list):
        items = data[wrapper]
        if not include_all_fields and entity in COMMON_FIELDS:
            items = _filter_fields(items, COMMON_FIELDS[entity])
        items = _augment_urls(items, entity, public_url)
        return {**data, wrapper: items}
    if not include_all_fields and entity in COMMON_FIELDS:
        data = _filter_fields(data, COMMON_FIELDS[entity])
    return _augment_urls(data, entity, public_url)


# Search responses nest the entity array under a plural key (e.g. asset -> "assets").
_PLURAL_KEYS: dict[str, str] = {
    "asset": "assets",
    "person": "people",
}


def _process_search(data: Any, entity: str, include_all_fields: bool, public_url: str) -> Any:
    """Variant of _process for search/metadata responses carrying nested {plural}.items."""
    container_key = _PLURAL_KEYS.get(entity, entity + "s")
    if isinstance(data, dict) and isinstance(data.get(container_key), dict):
        container = data[container_key]
        if isinstance(container, dict) and "items" in container:
            items = container["items"]
            if not include_all_fields and entity in COMMON_FIELDS:
                items = _filter_fields(items, COMMON_FIELDS[entity])
            items = _augment_urls(items, entity, public_url)
            data = {**data, container_key: {**container, "items": items}}
    elif not include_all_fields and entity in COMMON_FIELDS:
        data = _filter_fields(data, COMMON_FIELDS[entity])
        data = _augment_urls(data, entity, public_url)
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

    async def _maybe_filter(self, data: Any, key: str, include_all_fields: bool) -> Any:
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS[key])
        return data

    async def get_server_ping(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/ping", api_key), "server_ping", include_all_fields)

    async def get_server_version(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/version", api_key), "server_version", include_all_fields)

    async def get_server_about(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/about", api_key), "server_about", include_all_fields)

    async def get_server_config(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/config", api_key), "server_config", include_all_fields)

    async def get_server_features(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/features", api_key), "server_features", include_all_fields)

    async def get_server_statistics(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/statistics", api_key), "server_statistics", include_all_fields)

    async def get_server_storage(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/storage", api_key), "server_storage", include_all_fields)

    async def get_server_media_types(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/media-types", api_key), "server_media_types", include_all_fields)

    async def get_server_version_check(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/version-check", api_key), "server_version_check", include_all_fields)

    async def get_server_version_history(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/version-history", api_key), "server_version_history", include_all_fields)

    async def get_server_apk_links(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self._maybe_filter(await self.get("/server/apk-links", api_key), "server_apk_links", include_all_fields)

    # ==========================================================================
    # Asset Domain
    # ==========================================================================

    async def get_asset_by_id(
        self, asset_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/assets/{asset_id}", api_key)
        return _process(data, "asset", include_all_fields, self.public_url)

    async def get_asset_statistics(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/assets/statistics", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["asset_statistics"])
        return data

    async def get_asset_ocr(self, asset_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/assets/{asset_id}/ocr", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["asset_ocr"])
        return data

    async def get_asset_metadata(self, asset_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/assets/{asset_id}/metadata", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["asset_metadata"])
        return data

    async def get_asset_metadata_by_key(self, asset_id: str, key: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/assets/{asset_id}/metadata/{key}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["asset_metadata"])
        return data

    async def get_asset_edits(self, asset_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/assets/{asset_id}/edits", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["asset_edits"])
        return data

    async def get_asset_thumbnail_url(self, asset_id: str, api_key: Optional[str] = None) -> str:
        return f"{self.public_url}/api/assets/{asset_id}/thumbnail"

    async def get_asset_original_url(self, asset_id: str, api_key: Optional[str] = None) -> str:
        return f"{self.public_url}/api/assets/{asset_id}/original"

    async def update_asset(self, asset_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/assets/{asset_id}", api_key, json=payload)
        return _process(data, "asset", include_all_fields, self.public_url)

    async def update_asset_edits(self, asset_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/assets/{asset_id}/edits", api_key, json=payload)
        return _process(data, "asset", include_all_fields, self.public_url)

    async def update_asset_metadata(self, asset_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/assets/{asset_id}/metadata", api_key, json=payload)
        return _process(data, "asset", include_all_fields, self.public_url)

    async def delete_asset_metadata_by_key(self, asset_id: str, key: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/assets/{asset_id}/metadata/{key}", api_key)

    async def delete_assets(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete("/assets", api_key, json=payload)

    async def bulk_update_assets(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put("/assets", api_key, json=payload)
        return _process(data, "asset", include_all_fields, self.public_url)

    async def copy_asset(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put("/assets/copy", api_key, json=payload)
        return _process(data, "asset", include_all_fields, self.public_url)

    async def check_bulk_upload(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/assets/bulk-upload-check", api_key, json=payload)

    async def run_asset_jobs(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/assets/jobs", api_key, json=payload)

    async def run_job(self, job_id: str, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/jobs/{job_id}", api_key, json={"command": "start"})

    async def delete_asset_edits(self, asset_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/assets/{asset_id}/edits", api_key)

    async def get_asset_video_playback(self, asset_id: str, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/assets/{asset_id}/video/playback", api_key)

    async def get_asset_video_url(self, asset_id: str, api_key: Optional[str] = None) -> str:
        return f"{self.public_url}/api/assets/{asset_id}/video/playback"

    async def get_assets_by_tag(
        self, tag_id: str, api_key: Optional[str] = None,
        page: int = 1, size: int = 100,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.post(
            "/search/metadata", api_key,
            json={"tagIds": [tag_id], "page": page, "size": size},
        )
        return _process_search(data, "asset", include_all_fields, self.public_url)

    async def get_album_assets(
        self, album_id: str, api_key: Optional[str] = None,
        page: int = 1, size: int = 100,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.post(
            "/search/metadata", api_key,
            json={"albumIds": [album_id], "page": page, "size": size},
        )
        return _process_search(data, "asset", include_all_fields, self.public_url)

    async def get_memory_assets(
        self, memory_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/memories/{memory_id}", api_key)
        assets = data.get("assets", [])
        return _process(assets, "asset", include_all_fields, self.public_url)

    async def upload_asset(
        self,
        base64_data: str,
        device_asset_id: str,
        device_id: str,
        file_created_at: str,
        file_modified_at: str,
        api_key: Optional[str] = None,
        filename: str = "",
        duration: Optional[int] = None,
        is_favorite: Optional[bool] = None,
        visibility: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        file_bytes = base64.b64decode(base64_data)
        headers = {}
        if api_key:
            headers["x-api-key"] = api_key
        url = f"{self.base_url}/api/assets"
        files = {"assetData": (filename or "upload", file_bytes)}
        data: dict[str, Any] = {
            "deviceAssetId": device_asset_id,
            "deviceId": device_id,
            "fileCreatedAt": file_created_at,
            "fileModifiedAt": file_modified_at,
        }
        if filename:
            data["filename"] = filename
        if duration is not None:
            data["duration"] = duration
        if is_favorite is not None:
            data["isFavorite"] = str(is_favorite).lower()
        if visibility:
            data["visibility"] = visibility
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()
            result = response.json()
            return _process(result, "asset", include_all_fields, self.public_url)

    # ==========================================================================
    # Album Domain
    # ==========================================================================

    async def get_all_albums(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
        params: Optional[dict] = None,
    ) -> Any:
        data = await self.get("/albums", api_key, params=params)
        return _process(data, "album", include_all_fields, self.public_url)

    async def get_album_by_id(
        self, album_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/albums/{album_id}", api_key)
        return _process(data, "album", include_all_fields, self.public_url)

    async def create_album(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/albums", api_key, json=payload)
        return _process(data, "album", include_all_fields, self.public_url)

    async def update_album(self, album_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.patch(f"/albums/{album_id}", api_key, json=payload)
        return _process(data, "album", include_all_fields, self.public_url)

    async def delete_album_by_id(self, album_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/albums/{album_id}", api_key)

    async def add_assets_to_album(self, album_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/albums/{album_id}/assets", api_key, json=payload)
        return _process(data, "asset", include_all_fields, self.public_url)

    async def remove_assets_from_album(self, album_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/albums/{album_id}/assets", api_key, json=payload)

    async def add_users_to_album(self, album_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/albums/{album_id}/users", api_key, json=payload)
        return _process(data, "user", include_all_fields, self.public_url)

    async def update_user_role_in_album(self, album_id: str, user_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.put(f"/albums/{album_id}/user/{user_id}", api_key, json=payload)

    async def remove_user_from_album(self, album_id: str, user_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/albums/{album_id}/user/{user_id}", api_key)

    async def get_album_statistics(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/albums/statistics", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["album_statistics"])
        return data

    async def get_album_map_markers(self, album_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        try:
            data = await self.get(f"/albums/{album_id}/map-markers", api_key)
        except Exception:
            data = await self.get("/map/markers", api_key, params={"albumId": album_id})
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["map_markers"])
        return data

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

    async def create_tag(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/tags", api_key, json=payload)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

    async def update_tag(self, tag_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/tags/{tag_id}", api_key, json=payload)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

    async def delete_tag_by_id(self, tag_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/tags/{tag_id}", api_key)

    async def upsert_tags(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put("/tags", api_key, json=payload)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["tag"])
        return data

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
        return _process(data, "person", include_all_fields, self.public_url)

    async def get_person_by_id(
        self, person_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/people/{person_id}", api_key)
        return _process(data, "person", include_all_fields, self.public_url)

    async def create_person(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/people", api_key, json=payload)
        return _process(data, "person", include_all_fields, self.public_url)

    async def update_person(self, person_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/people/{person_id}", api_key, json=payload)
        return _process(data, "person", include_all_fields, self.public_url)

    async def delete_person_by_id(self, person_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/people/{person_id}", api_key)

    async def bulk_update_people(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put("/people", api_key, json=payload)
        return _process(data, "person", include_all_fields, self.public_url)

    async def bulk_delete_people(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete("/people", api_key, json=payload)

    async def merge_people(self, person_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post(f"/people/{person_id}/merge", api_key, json=payload)
        return _process(data, "person", include_all_fields, self.public_url)

    async def reassign_faces(self, person_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/people/{person_id}/reassign", api_key, json=payload)
        return _process(data, "person", include_all_fields, self.public_url)

    async def get_person_statistics(self, person_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/people/{person_id}/statistics", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["person_statistics"])
        return data

    async def get_person_thumbnail_url(self, person_id: str, api_key: Optional[str] = None) -> str:
        return f"{self.public_url}/api/people/{person_id}/thumbnail"

    async def get_faces_by_asset(self, asset_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/faces?id={asset_id}", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["faces"])
        return data

    async def create_face(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/faces", api_key, json=payload)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["faces"])
        return data

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
        return _process(data, "library", include_all_fields, self.public_url)

    async def get_library_by_id(
        self, library_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/libraries/{library_id}", api_key)
        return _process(data, "library", include_all_fields, self.public_url)

    async def create_library(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/libraries", api_key, json=payload)
        return _process(data, "library", include_all_fields, self.public_url)

    async def update_library(self, library_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/libraries/{library_id}", api_key, json=payload)
        return _process(data, "library", include_all_fields, self.public_url)

    async def delete_library_by_id(self, library_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/libraries/{library_id}", api_key)

    async def scan_library(self, library_id: str, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/libraries/{library_id}/scan", api_key)

    async def validate_library(self, library_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post(f"/libraries/{library_id}/validate", api_key, json=payload)

    async def get_library_statistics(self, library_id: str, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/libraries/{library_id}/statistics", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["library_statistics"])
        return data

    # ==========================================================================
    # Memory Domain
    # ==========================================================================

    async def get_all_memories(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/memories", api_key)
        return _process(data, "memory", include_all_fields, self.public_url)

    async def get_memory_by_id(
        self, memory_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/memories/{memory_id}", api_key)
        return _process(data, "memory", include_all_fields, self.public_url)

    async def create_memory(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/memories", api_key, json=payload)
        return _process(data, "memory", include_all_fields, self.public_url)

    async def update_memory(self, memory_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/memories/{memory_id}", api_key, json=payload)
        return _process(data, "memory", include_all_fields, self.public_url)

    async def delete_memory_by_id(self, memory_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/memories/{memory_id}", api_key)

    async def add_assets_to_memory(self, memory_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/memories/{memory_id}/assets", api_key, json=payload)
        return _process(data, "memory", include_all_fields, self.public_url)

    async def remove_assets_from_memory(self, memory_id: str, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/memories/{memory_id}/assets", api_key, json=payload)

    async def get_memory_statistics(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/memories/statistics", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["memory_statistics"])
        return data

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

    async def create_stack(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/stacks", api_key, json=payload)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["stack"])
        return data

    async def update_stack(self, stack_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/stacks/{stack_id}", api_key, json=payload)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["stack"])
        return data

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
        return _process(data, "shared_link", include_all_fields, self.public_url)

    async def get_shared_link_by_id(
        self, shared_link_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/shared-links/{shared_link_id}", api_key)
        return _process(data, "shared_link", include_all_fields, self.public_url)

    async def get_current_shared_link(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/shared-links/me", api_key)
        return _process(data, "shared_link", include_all_fields, self.public_url)

    async def create_shared_link(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/shared-links", api_key, json=payload)
        return _process(data, "shared_link", include_all_fields, self.public_url)

    async def update_shared_link(self, shared_link_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.patch(f"/shared-links/{shared_link_id}", api_key, json=payload)
        return _process(data, "shared_link", include_all_fields, self.public_url)

    async def delete_shared_link_by_id(self, shared_link_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/shared-links/{shared_link_id}", api_key)

    async def add_assets_to_shared_link(self, shared_link_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/shared-links/{shared_link_id}/assets", api_key, json=payload)
        return _process(data, "shared_link", include_all_fields, self.public_url)

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

    async def get_activity_statistics(self, api_key: Optional[str] = None, params: Optional[dict] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/activities/statistics", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["activity_statistics"])
        return data

    async def create_activity(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/activities", api_key, json=payload)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["activity"])
        return data

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
        return _process(data, "partner", include_all_fields, self.public_url)

    async def create_partner(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/partners", api_key, json=payload)
        return _process(data, "partner", include_all_fields, self.public_url)

    async def update_partner(self, partner_id: str, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put(f"/partners/{partner_id}", api_key, json=payload)
        return _process(data, "partner", include_all_fields, self.public_url)

    async def delete_partner_by_id(self, partner_id: str, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/partners/{partner_id}", api_key)

    # ==========================================================================
    # Search Domain
    # ==========================================================================

    async def search_metadata(
        self, payload: dict, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.post("/search/metadata", api_key, json=payload)
        return _process_search(data, "asset", include_all_fields, self.public_url)

    async def search_smart(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/search/smart", api_key, json=payload)
        return _process_search(data, "asset", include_all_fields, self.public_url)

    async def search_random(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/search/random", api_key, json=payload)
        return _process_search(data, "asset", include_all_fields, self.public_url)

    async def search_suggestions(self, params: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/search/suggestions", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["search_suggestions"])
        return data

    async def search_explore(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/search/explore", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["explore"])
        return data

    async def search_cities(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/search/cities", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["cities"])
        return data

    async def search_person(self, params: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/search/person", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["people"])
        return data

    async def search_places(self, params: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/search/places", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["places"])
        return data

    async def search_statistics(self, payload: dict, api_key: Optional[str] = None) -> Any:
        return await self.post("/search/statistics", api_key, json=payload)

    # ==========================================================================
    # Timeline & Map Domain
    # ==========================================================================

    async def get_time_buckets(self, params: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/timeline/buckets", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["time_buckets"])
        return data

    async def get_time_bucket(self, params: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/timeline/bucket", api_key, params=params)
        return _process(data, "asset", include_all_fields, self.public_url)

    async def get_map_markers(self, params: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/map/markers", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["map_markers"])
        return data

    async def reverse_geocode(self, params: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/map/reverse-geocode", api_key, params=params)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["geocode"])
        return data

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

    async def get_system_config(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/system-config", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["system_config"])
        return data

    async def get_system_config_defaults(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/system-config/defaults", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["system_config_defaults"])
        return data

    async def get_storage_template_options(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/system-config/storage-template-options", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["storage_template"])
        return data

    # ==========================================================================
    # User Domain
    # ==========================================================================

    async def get_all_users(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/users", api_key)
        return _process(data, "user", include_all_fields, self.public_url)

    async def get_user_by_id(
        self, user_id: str, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get(f"/users/{user_id}", api_key)
        return _process(data, "user", include_all_fields, self.public_url)

    async def get_my_user_info(
        self, api_key: Optional[str] = None,
        include_all_fields: bool = False,
    ) -> Any:
        data = await self.get("/users/me", api_key)
        return _process(data, "user", include_all_fields, self.public_url)

    async def update_my_user(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.put("/users/me", api_key, json=payload)
        return _process(data, "user", include_all_fields, self.public_url)

    async def get_my_preferences(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get("/users/me/preferences", api_key)
        if not include_all_fields:
            data = _filter_fields(data, COMMON_FIELDS["preferences"])
        return data

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
        return f"{self.public_url}/api/users/{user_id}/profile-image"

    async def delete_profile_image(self, api_key: Optional[str] = None) -> Any:
        return await self.delete("/users/profile-image", api_key)

    async def create_user(self, payload: dict, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.post("/admin/users", api_key, json=payload)
        return _process(data, "user", include_all_fields, self.public_url)

    async def delete_user(self, user_id: str, api_key: Optional[str] = None) -> Any:
        return await self.request("DELETE", f"/admin/users/{user_id}", api_key, json={})
