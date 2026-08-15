import json
import os
import sys
from contextvars import ContextVar
from typing import Any, Optional, Union

from fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from toon_mcp import json_to_toon

from .client import ImmichClient

_current_user_token: ContextVar[Optional[str]] = ContextVar("current_user_token", default=None)

ALLOW_ALL_AGGREGATE = os.getenv("ALLOW_ALL_AGGREGATE", "false").lower() in ("true", "1", "yes")
IS_STATEFUL = os.getenv("IS_STATEFUL", "false").lower() in ("true", "1", "yes")


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                _current_user_token.set(token)
        await self.app(scope, receive, send)


mcp = FastMCP("immich-mcp-server")

_client: Optional[ImmichClient] = None


def get_client() -> ImmichClient:
    global _client
    if _client is None:
        _client = ImmichClient()
    return _client


def get_user_token() -> Optional[str]:
    return _current_user_token.get()


def _normalize_datetime(value: str) -> str:
    import re, datetime as dt
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$', value):
        parsed = dt.datetime.fromisoformat(value)
        parsed = parsed.astimezone(dt.timezone.utc)
        return parsed.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value):
        raise ValueError("Timezone offset required. Use 2026-06-22T15:00:00-04:00")
    return value


def _norm_datetime_in_dict(data: dict) -> dict:
    return {k: _normalize_datetime(v) if isinstance(v, str) and 'T' in v else v for k, v in data.items()}


# =============================================================================
# Pydantic Contract Models
# =============================================================================

class CreateAlbumParam(BaseModel):
    albumName: str
    description: str = ""
    albumUsers: str = ""
    assetIds: str = ""

class UpdateAlbumParam(BaseModel):
    albumName: Optional[str] = None
    description: Optional[str] = None
    albumThumbnailAssetId: Optional[str] = None
    isActivityEnabled: Optional[bool] = None
    order: Optional[str] = None

class AddAssetsToAlbumParam(BaseModel):
    assetIds: list[str]

class AddUsersToAlbumParam(BaseModel):
    albumUsers: list[dict]

class UpdateUserRoleParam(BaseModel):
    role: str

class CreateTagParam(BaseModel):
    name: str
    color: str = ""
    parentId: str = ""

class UpdateTagParam(BaseModel):
    color: Optional[str] = None

class TagAssetsParam(BaseModel):
    assetIds: list[str]
    tagIds: list[str]

class UpsertTagsParam(BaseModel):
    tags: list[str]

class CreateLibraryParam(BaseModel):
    ownerId: str
    name: str = ""
    importPaths: str = ""
    exclusionPatterns: str = ""

class UpdateLibraryParam(BaseModel):
    name: Optional[str] = None
    importPaths: Optional[str] = None
    exclusionPatterns: Optional[str] = None

class CreateMemoryParam(BaseModel):
    type: str
    memoryAt: str
    data: str
    assetIds: str = ""
    isSaved: bool = False
    hideAt: str = ""
    showAt: str = ""
    seenAt: str = ""

class UpdateMemoryParam(BaseModel):
    isSaved: Optional[bool] = None
    memoryAt: Optional[str] = None
    seenAt: Optional[str] = None

class CreateStackParam(BaseModel):
    assetIds: list[str]

class UpdateStackParam(BaseModel):
    primaryAssetId: Optional[str] = None

class CreateSharedLinkParam(BaseModel):
    type: str
    assetIds: str = ""
    albumId: str = ""
    description: str = ""
    expiresAt: str = ""
    password: str = ""
    allowDownload: bool = True
    allowUpload: bool = False
    showMetadata: bool = True
    slug: str = ""

class UpdateSharedLinkParam(BaseModel):
    description: Optional[str] = None
    expiresAt: Optional[str] = None
    password: Optional[str] = None
    allowDownload: Optional[bool] = None
    allowUpload: Optional[bool] = None
    showMetadata: Optional[bool] = None
    slug: Optional[str] = None

class CreateActivityParam(BaseModel):
    albumId: str
    type: str
    assetId: str = ""
    comment: str = ""

class CreatePartnerParam(BaseModel):
    sharedWithId: str

class UpdatePartnerParam(BaseModel):
    inTimeline: bool

class CreatePersonParam(BaseModel):
    name: str = ""
    birthDate: str = ""
    color: str = ""
    isFavorite: bool = False
    isHidden: bool = False

class UpdatePersonParam(BaseModel):
    name: Optional[str] = None
    birthDate: Optional[str] = None
    color: Optional[str] = None
    isFavorite: Optional[bool] = None
    isHidden: Optional[bool] = None
    featureFaceAssetId: Optional[str] = None

class BulkUpdatePeopleItem(BaseModel):
    id: str
    name: Optional[str] = None
    birthDate: Optional[str] = None
    color: Optional[str] = None
    isFavorite: Optional[bool] = None
    isHidden: Optional[bool] = None
    featureFaceAssetId: Optional[str] = None

class MergePersonParam(BaseModel):
    ids: list[str]

class ReassignFacesParam(BaseModel):
    assetFaceUpdateItems: list[dict]

class BulkIdsParam(BaseModel):
    ids: list[str]

class AssetBulkUpdateParam(BaseModel):
    ids: list[str]
    isFavorite: Optional[bool] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    dateTimeOriginal: Optional[str] = None
    rating: Optional[int] = None
    visibility: Optional[str] = None
    duplicateId: Optional[str] = None
    timeZone: Optional[str] = None

class UpdateAssetParam(BaseModel):
    isFavorite: Optional[bool] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    dateTimeOriginal: Optional[str] = None
    rating: Optional[int] = None
    visibility: Optional[str] = None
    livePhotoVideoId: Optional[str] = None

class CopyAssetParam(BaseModel):
    sourceId: str
    targetId: str
    albums: bool = False
    favorite: bool = False
    sharedLinks: bool = False
    sidecar: bool = False
    stack: bool = False

class SearchMetadataParam(BaseModel):
    page: int = 1
    size: int = 100
    type: Optional[str] = None
    query: Optional[str] = None
    isFavorite: Optional[bool] = None
    isArchived: Optional[bool] = None
    isMotion: Optional[bool] = None
    isOffline: Optional[bool] = None
    isNotInAlbum: Optional[bool] = None
    trashedAfter: Optional[str] = None
    trashedBefore: Optional[str] = None
    takenAfter: Optional[str] = None
    takenBefore: Optional[str] = None
    updatedAfter: Optional[str] = None
    updatedBefore: Optional[str] = None
    createdAfter: Optional[str] = None
    createdBefore: Optional[str] = None
    originalFileName: Optional[str] = None
    originalPath: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    lensModel: Optional[str] = None
    checksum: Optional[str] = None
    description: Optional[str] = None
    ocr: Optional[str] = None
    rating: Optional[int] = None
    personIds: str = ""
    tagIds: str = ""
    albumIds: str = ""
    libraryId: Optional[str] = None
    order: Optional[str] = None
    withExif: bool = False
    withPeople: bool = False
    withStacked: bool = False
    withDeleted: bool = False
    isEncoded: Optional[bool] = None
    encodedVideoPath: Optional[str] = None
    previewPath: Optional[str] = None
    thumbnailPath: Optional[str] = None
    id: Optional[str] = None

class SmartSearchParam(BaseModel):
    query: str
    page: int = 1
    size: int = 100
    type: Optional[str] = None
    isFavorite: Optional[bool] = None
    isArchived: Optional[bool] = None
    isMotion: Optional[bool] = None
    isOffline: Optional[bool] = None
    isNotInAlbum: Optional[bool] = None
    trashedAfter: Optional[str] = None
    trashedBefore: Optional[str] = None
    takenAfter: Optional[str] = None
    takenBefore: Optional[str] = None
    updatedAfter: Optional[str] = None
    updatedBefore: Optional[str] = None
    createdAfter: Optional[str] = None
    createdBefore: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    lensModel: Optional[str] = None
    ocr: Optional[str] = None
    rating: Optional[int] = None
    personIds: str = ""
    tagIds: str = ""
    albumIds: str = ""
    libraryId: Optional[str] = None
    queryAssetId: Optional[str] = None
    language: Optional[str] = None
    withExif: bool = False
    withDeleted: bool = False
    visibility: Optional[str] = None
    isEncoded: Optional[bool] = None

class UpdateMyUserParam(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None
    avatarColor: Optional[str] = None

class UpdateMyPreferencesParam(BaseModel):
    preferences: dict


class AssetMetadataEntry(BaseModel):
    key: str = Field(description="Metadata key (e.g. 'mobile-app').")
    value: dict = Field(description="Metadata value as an arbitrary JSON object (e.g. {'someField': 'someValue'}).")


class CropParameters(BaseModel):
    x: int = Field(description="Top-left X coordinate in pixels.")
    y: int = Field(description="Top-left Y coordinate in pixels.")
    width: int = Field(description="Width of the crop rectangle in pixels.")
    height: int = Field(description="Height of the crop rectangle in pixels.")


class RotateParameters(BaseModel):
    angle: float = Field(description="0, 90, 180, or 270.")


class MirrorParameters(BaseModel):
    axis: str = Field(description="horizontal or vertical.")


class AssetEditItem(BaseModel):
    action: str = Field(description="crop, rotate, or mirror.")
    parameters: Union[CropParameters, RotateParameters, MirrorParameters] = Field(
        description="Parameters for the edit action. Use the matching parameters type for the chosen action."
    )


# Preferences are passed as flat parameters in update_my_preferences

# =============================================================================
# Server Tools
# =============================================================================

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get Server Ping", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_server_ping(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Check if the Immich server is reachable.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_server_ping(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get Server Version", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_server_version(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get the Immich server version.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_server_version(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get Server About", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_server_about(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get general server information.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_server_about(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get Server Config", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_server_config(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get the server configuration settings.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_server_config(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get Server Features", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_server_features(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get the server feature flags.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_server_features(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get Server Statistics", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_server_statistics(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get server usage statistics.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_server_statistics(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get Server Storage", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_server_storage(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get server storage information.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_server_storage(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Server Media Types", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_server_media_types(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get supported media types.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_server_media_types(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get Server Version Check", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_server_version_check(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get version check status.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_server_version_check(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="List Server Version History", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_server_version_history(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get version history."""
    result = await get_client().get_server_version_history(
        get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
    )
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Server Apk Links", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_server_apk_links(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get APK download links.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_server_apk_links(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

# =============================================================================
# Asset Tools
# =============================================================================

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get Asset By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_asset_by_id(
id: str,
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get a single asset by its ID.

    Args:
        id: The unique ID of the asset.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_asset_by_id(
        id, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get Asset Statistics", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_asset_statistics(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get asset statistics (total count, image/video counts).

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_asset_statistics(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get Asset Exif", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_asset_exif(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get EXIF data for an asset.

    Args:
        id: The unique ID of the asset.
    """
    data = await get_client().get_asset_by_id(id, get_user_token(), include_all_fields=True)
    exif = data.get("exifInfo", {})
    return {"exifInfo": exif}

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Asset Ocr", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_asset_ocr(
    id: str,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get OCR data for an asset.

    Args:
        id: The unique ID of the asset.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_asset_ocr(id, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Asset Metadata", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_asset_metadata(
    id: str,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get metadata for an asset.

    Args:
        id: The unique ID of the asset.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_asset_metadata(id, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Asset Metadata By Key", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_asset_metadata_by_key(
    id: str,
    key: str,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get specific metadata key for an asset.

    Args:
        id: The unique ID of the asset.
        key: The metadata key.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_asset_metadata_by_key(id, key, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Asset Edits", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_asset_edits(
    id: str,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get edit history for an asset.

    Args:
        id: The unique ID of the asset.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_asset_edits(id, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get Asset Thumbnail Url", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_asset_thumbnail_url(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get the URL to view an asset's thumbnail.

    Args:
        id: The unique ID of the asset.
    """
    url = await get_client().get_asset_thumbnail_url(id, get_user_token())
    return {"url": url}

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get Asset Original Url", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_asset_original_url(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get the URL to download an asset's original file.

    Args:
        id: The unique ID of the asset.
    """
    url = await get_client().get_asset_original_url(id, get_user_token())
    return {"url": url}

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get Asset Video Url", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_asset_video_url(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get the URL to play an asset's video.

    Args:
        id: The unique ID of the asset.
    """
    url = await get_client().get_asset_video_url(id, get_user_token())
    return {"url": url}

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Update Asset", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_asset(
id: str,
ctx: Context,
isFavorite: Optional[bool] = None,
description: Optional[str] = None,
latitude: Optional[float] = None,
longitude: Optional[float] = None,
dateTimeOriginal: Optional[str] = None,
rating: Optional[int] = None,
visibility: Optional[str] = None,
livePhotoVideoId: Optional[str] = None,
) -> dict[str, Any]:
    """Update an asset's properties.

    Args:
        id: The unique ID of the asset.
        isFavorite: True to mark as favorite.
        description: Asset description.
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        dateTimeOriginal: ISO 8601 format (2026-06-22T15:00:00-04:00).
        rating: Rating in range [1-5] (starred), -1 (rejected), or null (unrated).
        visibility: Asset visibility: archive, timeline, hidden, or locked.
        livePhotoVideoId: Live photo video ID.
    """
    params = UpdateAssetParam(
        isFavorite=isFavorite, description=description,
        latitude=latitude, longitude=longitude,
        dateTimeOriginal=dateTimeOriginal, rating=rating,
        visibility=visibility, livePhotoVideoId=livePhotoVideoId,
    )
    return await get_client().update_asset(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Update Asset Edits", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_asset_edits(
    id: str,
    edits: list[AssetEditItem],
    ctx: Context,
) -> dict[str, Any]:
    """Apply edits to an existing asset.

    Args:
        id: The unique ID of the asset.
        edits: List of edit operations to apply. Each item has an action
            ('crop', 'rotate', or 'mirror') and corresponding parameters.
    """
    payload = {"edits": [e.model_dump() for e in edits]}
    return await get_client().update_asset_edits(id, payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Update Asset Metadata", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_asset_metadata(
    id: str,
    items: list[AssetMetadataEntry],
    ctx: Context,
) -> dict[str, Any]:
    """Update metadata for an asset.

    Args:
        id: The unique ID of the asset.
        items: List of metadata entries. Each entry has a key (string) and
            value (arbitrary JSON object, e.g. {'someField': 'someValue'}).
    """
    payload = {"items": [{"key": i.key, "value": i.value} for i in items]}
    result = await get_client().update_asset_metadata(id, payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Delete Assets", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_assets(
ids: list[str],
ctx: Context,
force: bool = False,
) -> dict[str, Any]:
    """Delete assets by IDs.

    Args:
        ids: List of asset IDs to delete.
        force: Force delete even if in trash.
    """
    payload = {"ids": ids}
    if force:
        payload["force"] = True
    return await get_client().delete_assets(payload, get_user_token())

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Bulk Update Assets", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def bulk_update_assets(
ids: list[str],
ctx: Context,
isFavorite: Optional[bool] = None,
description: Optional[str] = None,
latitude: Optional[float] = None,
longitude: Optional[float] = None,
dateTimeOriginal: Optional[str] = None,
rating: Optional[int] = None,
visibility: Optional[str] = None,
duplicateId: Optional[str] = None,
timeZone: Optional[str] = None,
) -> dict[str, Any]:
    """Update multiple assets at once.

    Args:
        ids: List of asset IDs to update.
        isFavorite: True to mark as favorite.
        description: Asset description.
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        dateTimeOriginal: ISO 8601 format (2026-06-22T15:00:00-04:00).
        rating: Rating in range [1-5], -1, or null.
        visibility: Asset visibility: archive, timeline, hidden, or locked.
        duplicateId: Set to assign asset to a duplicate group, or null to remove from group.
        timeZone: Time zone in IANA format (e.g. America/New_York).
    """
    params = AssetBulkUpdateParam(
        ids=ids,
        isFavorite=isFavorite, description=description,
        latitude=latitude, longitude=longitude,
        dateTimeOriginal=dateTimeOriginal, rating=rating,
        visibility=visibility, duplicateId=duplicateId, timeZone=timeZone,
    )
    return await get_client().bulk_update_assets(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Copy Asset", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def copy_asset(
sourceId: str,
targetId: str,
ctx: Context,
albums: bool = False,
favorite: bool = False,
sharedLinks: bool = False,
sidecar: bool = False,
stack: bool = False,
) -> dict[str, Any]:
    """Copy metadata from one asset to another.

    Args:
        sourceId: Source asset ID.
        targetId: Target asset ID.
        albums: Copy album associations.
        favorite: Copy favorite status.
        sharedLinks: Copy shared links.
        sidecar: Copy associated sidecar metadata file (.xmp).
        stack: Copy stack association.
    """
    params = CopyAssetParam(
        sourceId=sourceId, targetId=targetId,
        albums=albums, favorite=favorite,
        sharedLinks=sharedLinks, sidecar=sidecar, stack=stack,
    )
    return await get_client().copy_asset(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="List All Assets", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_assets(
    ctx: Context,
    page: int = 1,
    size: int = 100,
    include_all_fields: bool = False,
    type: Optional[str] = None,
    isFavorite: Optional[bool] = None,
    isMotion: Optional[bool] = None,
    isOffline: Optional[bool] = None,
    isNotInAlbum: Optional[bool] = None,
    takenAfter: Optional[str] = None,
    takenBefore: Optional[str] = None,
    originalFileName: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    personIds: list[str] = [],
    tagIds: list[str] = [],
    albumIds: list[str] = [],
    libraryId: Optional[str] = None,
    order: Optional[str] = None,
    withExif: bool = False,
    withPeople: bool = False,
    withStacked: bool = False,
) -> dict[str, Any]:
    """List every photo, video, and audio file in the library. Returns thumbnails, file metadata, playback URLs, and owner info for each asset.

    Args:
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 100.
        include_all_fields: Default False (common fields only). Set True for all fields.
        type: IMAGE, VIDEO, AUDIO, or OTHER.
        isFavorite: Filter by favorite status.
        isMotion: Filter by motion photo.
        isOffline: Filter by offline status.
        isNotInAlbum: Filter assets not in any album.
        takenAfter: Filter by taken date after. ISO 8601 format (2026-06-22T15:00:00-04:00).
        takenBefore: Filter by taken date before. ISO 8601 format (2026-06-22T15:00:00-04:00).
        originalFileName: Filter by original file name.
        city: Filter by city name.
        state: Filter by state/province name.
        country: Filter by country name.
        make: Filter by camera make (e.g. Canon, Apple).
        model: Filter by camera model (e.g. EOS R5, iPhone 15).
        personIds: List of person IDs.
        tagIds: List of tag IDs.
        albumIds: List of album IDs.
        libraryId: Library ID to filter by.
        order: asc or desc.
        withExif: Include EXIF data.
        withPeople: Include people data.
        withStacked: Include stacked assets.
    """
    return await _list_assets_by_type(
        type=type, page=page, size=size, include_all_fields=include_all_fields,
        isFavorite=isFavorite, isMotion=isMotion, isOffline=isOffline,
        isNotInAlbum=isNotInAlbum, takenAfter=takenAfter, takenBefore=takenBefore,
        originalFileName=originalFileName, city=city, state=state, country=country,
        make=make, model=model, personIds=personIds, tagIds=tagIds, albumIds=albumIds,
        libraryId=libraryId, order=order, withExif=withExif, withPeople=withPeople,
        withStacked=withStacked,
    )


async def _list_assets_by_type(
    type: Optional[str],
    page: int,
    size: int,
    include_all_fields: bool,
    isFavorite: Optional[bool],
    isMotion: Optional[bool],
    isOffline: Optional[bool],
    isNotInAlbum: Optional[bool],
    takenAfter: Optional[str],
    takenBefore: Optional[str],
    originalFileName: Optional[str],
    city: Optional[str],
    state: Optional[str],
    country: Optional[str],
    make: Optional[str],
    model: Optional[str],
    personIds: list[str],
    tagIds: list[str],
    albumIds: list[str],
    libraryId: Optional[str],
    order: Optional[str],
    withExif: bool,
    withPeople: bool,
    withStacked: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"page": page, "size": size}
    if type: payload["type"] = type
    if isFavorite is not None: payload["isFavorite"] = isFavorite
    if isMotion is not None: payload["isMotion"] = isMotion
    if isOffline is not None: payload["isOffline"] = isOffline
    if isNotInAlbum is not None: payload["isNotInAlbum"] = isNotInAlbum
    if takenAfter: payload["takenAfter"] = takenAfter
    if takenBefore: payload["takenBefore"] = takenBefore
    if originalFileName: payload["originalFileName"] = originalFileName
    if city: payload["city"] = city
    if state: payload["state"] = state
    if country: payload["country"] = country
    if make: payload["make"] = make
    if model: payload["model"] = model
    if personIds: payload["personIds"] = personIds
    if tagIds: payload["tagIds"] = tagIds
    if albumIds: payload["albumIds"] = albumIds
    if libraryId: payload["libraryId"] = libraryId
    if order: payload["order"] = order
    if withExif: payload["withExif"] = True
    if withPeople: payload["withPeople"] = True
    if withStacked: payload["withStacked"] = True
    return await get_client().search_metadata(
        payload, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
    )


async def _list_asset_widget(
    ctx: Context,
    type: str,
    page: int,
    size: int,
    include_all_fields: bool,
    isFavorite: Optional[bool],
    isMotion: Optional[bool],
    isOffline: Optional[bool],
    isNotInAlbum: Optional[bool],
    takenAfter: Optional[str],
    takenBefore: Optional[str],
    originalFileName: Optional[str],
    city: Optional[str],
    state: Optional[str],
    country: Optional[str],
    make: Optional[str],
    model: Optional[str],
    personIds: list[str],
    tagIds: list[str],
    albumIds: list[str],
    libraryId: Optional[str],
    order: Optional[str],
    withExif: bool,
    withPeople: bool,
    withStacked: bool,
) -> dict[str, Any]:
    return await _list_assets_by_type(
        type=type, page=page, size=size, include_all_fields=include_all_fields,
        isFavorite=isFavorite, isMotion=isMotion, isOffline=isOffline,
        isNotInAlbum=isNotInAlbum, takenAfter=takenAfter, takenBefore=takenBefore,
        originalFileName=originalFileName, city=city, state=state, country=country,
        make=make, model=model, personIds=personIds, tagIds=tagIds, albumIds=albumIds,
        libraryId=libraryId, order=order, withExif=withExif, withPeople=withPeople,
        withStacked=withStacked,
    )


@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="List All Photos", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_photos(
    ctx: Context,
    page: int = 1,
    size: int = 100,
    include_all_fields: bool = False,
    isFavorite: Optional[bool] = None,
    isMotion: Optional[bool] = None,
    isOffline: Optional[bool] = None,
    isNotInAlbum: Optional[bool] = None,
    takenAfter: Optional[str] = None,
    takenBefore: Optional[str] = None,
    originalFileName: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    personIds: list[str] = [],
    tagIds: list[str] = [],
    albumIds: list[str] = [],
    libraryId: Optional[str] = None,
    order: Optional[str] = None,
    withExif: bool = False,
    withPeople: bool = False,
    withStacked: bool = False,
) -> dict[str, Any]:
    """List all photo (IMAGE) assets. Returns thumbnails, file metadata, playback URLs, and owner info for each asset.

    Args:
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 100.
        include_all_fields: Default False (common fields only). Set True for all fields.
        isFavorite: Filter by favorite status.
        isMotion: Filter by motion photo.
        isOffline: Filter by offline status.
        isNotInAlbum: Filter assets not in any album.
        takenAfter: Filter by taken date after. ISO 8601 format (2026-06-22T15:00:00-04:00).
        takenBefore: Filter by taken date before. ISO 8601 format (2026-06-22T15:00:00-04:00).
        originalFileName: Filter by original file name.
        city: Filter by city name.
        state: Filter by state/province name.
        country: Filter by country name.
        make: Filter by camera make (e.g. Canon, Apple).
        model: Filter by camera model (e.g. EOS R5, iPhone 15).
        personIds: List of person IDs.
        tagIds: List of tag IDs.
        albumIds: List of album IDs.
        libraryId: Library ID to filter by.
        order: asc or desc.
        withExif: Include EXIF data.
        withPeople: Include people data.
        withStacked: Include stacked assets.
    """
    return await _list_asset_widget(
        ctx=ctx, type="IMAGE", page=page, size=size, include_all_fields=include_all_fields,
        isFavorite=isFavorite, isMotion=isMotion, isOffline=isOffline,
        isNotInAlbum=isNotInAlbum, takenAfter=takenAfter, takenBefore=takenBefore,
        originalFileName=originalFileName, city=city, state=state, country=country,
        make=make, model=model, personIds=personIds, tagIds=tagIds, albumIds=albumIds,
        libraryId=libraryId, order=order, withExif=withExif, withPeople=withPeople,
        withStacked=withStacked,
    )


@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="List All Videos", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_videos(
    ctx: Context,
    page: int = 1,
    size: int = 100,
    include_all_fields: bool = False,
    isFavorite: Optional[bool] = None,
    isMotion: Optional[bool] = None,
    isOffline: Optional[bool] = None,
    isNotInAlbum: Optional[bool] = None,
    takenAfter: Optional[str] = None,
    takenBefore: Optional[str] = None,
    originalFileName: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    personIds: list[str] = [],
    tagIds: list[str] = [],
    albumIds: list[str] = [],
    libraryId: Optional[str] = None,
    order: Optional[str] = None,
    withExif: bool = False,
    withPeople: bool = False,
    withStacked: bool = False,
) -> dict[str, Any]:
    """List all video (VIDEO) assets. Returns thumbnails, file metadata, playback URLs, and owner info for each asset.

    Args:
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 100.
        include_all_fields: Default False (common fields only). Set True for all fields.
        isFavorite: Filter by favorite status.
        isMotion: Filter by motion photo.
        isOffline: Filter by offline status.
        isNotInAlbum: Filter assets not in any album.
        takenAfter: Filter by taken date after. ISO 8601 format (2026-06-22T15:00:00-04:00).
        takenBefore: Filter by taken date before. ISO 8601 format (2026-06-22T15:00:00-04:00).
        originalFileName: Filter by original file name.
        city: Filter by city name.
        state: Filter by state/province name.
        country: Filter by country name.
        make: Filter by camera make (e.g. Canon, Apple).
        model: Filter by camera model (e.g. EOS R5, iPhone 15).
        personIds: List of person IDs.
        tagIds: List of tag IDs.
        albumIds: List of album IDs.
        libraryId: Library ID to filter by.
        order: asc or desc.
        withExif: Include EXIF data.
        withPeople: Include people data.
        withStacked: Include stacked assets.
    """
    return await _list_asset_widget(
        ctx=ctx, type="VIDEO", page=page, size=size, include_all_fields=include_all_fields,
        isFavorite=isFavorite, isMotion=isMotion, isOffline=isOffline,
        isNotInAlbum=isNotInAlbum, takenAfter=takenAfter, takenBefore=takenBefore,
        originalFileName=originalFileName, city=city, state=state, country=country,
        make=make, model=model, personIds=personIds, tagIds=tagIds, albumIds=albumIds,
        libraryId=libraryId, order=order, withExif=withExif, withPeople=withPeople,
        withStacked=withStacked,
    )


@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="List All Other Assets", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_other(
    ctx: Context,
    page: int = 1,
    size: int = 100,
    include_all_fields: bool = False,
    isFavorite: Optional[bool] = None,
    isMotion: Optional[bool] = None,
    isOffline: Optional[bool] = None,
    isNotInAlbum: Optional[bool] = None,
    takenAfter: Optional[str] = None,
    takenBefore: Optional[str] = None,
    originalFileName: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    personIds: list[str] = [],
    tagIds: list[str] = [],
    albumIds: list[str] = [],
    libraryId: Optional[str] = None,
    order: Optional[str] = None,
    withExif: bool = False,
    withPeople: bool = False,
    withStacked: bool = False,
) -> dict[str, Any]:
    """List all OTHER assets (audio, sidecar (.xmp), and unrecognized non-image/video files). Returns thumbnails, file metadata, playback URLs, and owner info for each asset.

    Args:
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 100.
        include_all_fields: Default False (common fields only). Set True for all fields.
        isFavorite: Filter by favorite status.
        isMotion: Filter by motion photo.
        isOffline: Filter by offline status.
        isNotInAlbum: Filter assets not in any album.
        takenAfter: Filter by taken date after. ISO 8601 format (2026-06-22T15:00:00-04:00).
        takenBefore: Filter by taken date before. ISO 8601 format (2026-06-22T15:00:00-04:00).
        originalFileName: Filter by original file name.
        city: Filter by city name.
        state: Filter by state/province name.
        country: Filter by country name.
        make: Filter by camera make (e.g. Canon, Apple).
        model: Filter by camera model (e.g. EOS R5, iPhone 15).
        personIds: List of person IDs.
        tagIds: List of tag IDs.
        albumIds: List of album IDs.
        libraryId: Library ID to filter by.
        order: asc or desc.
        withExif: Include EXIF data.
        withPeople: Include people data.
        withStacked: Include stacked assets.
    """
    return await _list_asset_widget(
        ctx=ctx, type="OTHER", page=page, size=size, include_all_fields=include_all_fields,
        isFavorite=isFavorite, isMotion=isMotion, isOffline=isOffline,
        isNotInAlbum=isNotInAlbum, takenAfter=takenAfter, takenBefore=takenBefore,
        originalFileName=originalFileName, city=city, state=state, country=country,
        make=make, model=model, personIds=personIds, tagIds=tagIds, albumIds=albumIds,
        libraryId=libraryId, order=order, withExif=withExif, withPeople=withPeople,
        withStacked=withStacked,
    )


@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List Assets By Tag", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_assets_by_tag(
    tagId: str,
    ctx: Context,
    page: int = 1,
    size: int = 100,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get all assets that have a specific tag.

    Args:
        tagId: The unique ID of the tag.
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 100.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_assets_by_tag(
        tagId, get_user_token(), page=page, size=size,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List Assets By Album", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_assets_by_album(
    albumId: str,
    ctx: Context,
    page: int = 1,
    size: int = 100,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get all assets in an album.

    Args:
        albumId: The unique ID of the album.
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 100.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_album_assets(
        albumId, get_user_token(), page=page, size=size,
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List Assets By Memory", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_assets_by_memory(
    memoryId: str,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get all assets in a memory.

    Args:
        memoryId: The unique ID of the memory.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_memory_assets(
        memoryId, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Upload Asset", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def upload_asset(
    base64_data: str,
    deviceAssetId: str,
    deviceId: str,
    fileCreatedAt: str,
    fileModifiedAt: str,
    ctx: Context,
    filename: str = "",
    duration: Optional[int] = None,
    isFavorite: Optional[bool] = None,
    visibility: Optional[str] = None,
) -> dict[str, Any]:
    """Upload an asset from base64-encoded data.

    Args:
        base64_data: Base64-encoded file data.
        deviceAssetId: Unique asset ID for the device.
        deviceId: Device identifier.
        fileCreatedAt: File creation timestamp ISO 8601 format (2026-06-22T15:00:00-04:00).
        fileModifiedAt: File modification timestamp ISO 8601 format (2026-06-22T15:00:00-04:00).
        filename: Original filename.
        duration: Duration in seconds (for video assets).
        isFavorite: True to mark as favorite.
        visibility: Asset visibility: archive, timeline, hidden, or locked.
    """
    return await get_client().upload_asset(
        base64_data, deviceAssetId, deviceId, fileCreatedAt, fileModifiedAt, get_user_token(),
        filename=filename, duration=duration,
        is_favorite=isFavorite, visibility=visibility, include_all_fields=ALLOW_ALL_AGGREGATE,
    )

# =============================================================================
# Album Tools
# =============================================================================

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="List All Albums", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_albums(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List all albums.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_all_albums(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get Album By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_album_by_id(
id: str,
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get a single album by ID.

    Args:
        id: The unique ID of the album.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_album_by_id(
        id, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Create Album", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_album(
albumName: str,
ctx: Context,
description: str = "",
albumUsers: list[str] = [],
assetIds: list[str] = [],
) -> dict[str, Any]:
    """Create a new album.

    Args:
        albumName: Name of the album.
        description: Description of the album.
        albumUsers: List of user IDs to share with.
        assetIds: List of asset IDs to add initially.
    """
    users_list = [{"userId": u} for u in albumUsers]
    params = CreateAlbumParam(albumName=albumName, description=description)
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    if users_list:
        payload["albumUsers"] = users_list
    if assetIds:
        payload["assetIds"] = assetIds
    return await get_client().create_album(payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Update Album", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_album(
id: str,
ctx: Context,
albumName: Optional[str] = None,
description: Optional[str] = None,
albumThumbnailAssetId: Optional[str] = None,
isActivityEnabled: Optional[bool] = None,
order: Optional[str] = None,
) -> dict[str, Any]:
    """Update an album.

    Args:
        id: The unique ID of the album.
        albumName: New album name.
        description: New album description.
        albumThumbnailAssetId: Asset ID for the album thumbnail.
        isActivityEnabled: True to enable activity feed.
        order: asc or desc.
    """
    params = UpdateAlbumParam(
        albumName=albumName, description=description,
        albumThumbnailAssetId=albumThumbnailAssetId,
        isActivityEnabled=isActivityEnabled, order=order,
    )
    return await get_client().update_album(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Delete Album By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_album_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete an album by ID.

    Args:
        id: The unique ID of the album to delete.
    """
    return await get_client().delete_album_by_id(id, get_user_token())

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Add Assets To Album", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def add_assets_to_album(
    id: str,
    assetIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Add assets to an album.

    Args:
        id: The unique ID of the album.
        assetIds: List of asset IDs.
    """
    payload = {"ids": assetIds}
    data = await get_client().add_assets_to_album(id, payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Remove Assets From Album", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def remove_assets_from_album(
    id: str,
    assetIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Remove assets from an album.

    Args:
        id: The unique ID of the album.
        assetIds: List of asset IDs.
    """
    payload = {"ids": assetIds}
    data = await get_client().remove_assets_from_album(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Share Album With Users", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def share_album_with_users(
    id: str,
    albumUsers: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Share an album with other users.

    Args:
        id: The unique ID of the album.
        albumUsers: List of user IDs to share with.
    """
    users_list = [{"userId": u} for u in albumUsers]
    payload = {"albumUsers": users_list}
    return await get_client().add_users_to_album(id, payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Remove User From Album", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def remove_user_from_album(
    id: str,
    userId: str,
    ctx: Context
) -> dict[str, Any]:
    """Remove a user from an album.

    Args:
        id: The unique ID of the album.
        userId: The user ID to remove.
    """
    return await get_client().remove_user_from_album(id, userId, get_user_token())

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Album Statistics", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_album_statistics(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get album statistics.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_album_statistics(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List Album Map Markers", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_album_map_markers(
    id: str,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get map markers for an album.

    Args:
        id: The unique ID of the album.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_album_map_markers(id, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": data} if isinstance(data, list) else data

# =============================================================================
# Tag Tools
# =============================================================================

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="List All Tags", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_tags(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List all tags.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_all_tags(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get Tag By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_tag_by_id(
id: str,
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get a single tag by ID.

    Args:
        id: The unique ID of the tag.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_tag_by_id(
        id, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Create Tag", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_tag(
name: str,
ctx: Context,
color: str = "",
parentId: str = "",
) -> dict[str, Any]:
    """Create a new tag.

    Args:
        name: Tag name.
        color: Tag color in hex format (e.g. #FF0000).
        parentId: Parent tag ID.
    """
    payload = {"name": name}
    if color:
        payload["color"] = color
    if parentId:
        payload["parentId"] = parentId
    return await get_client().create_tag(payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Update Tag", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_tag(
id: str,
ctx: Context,
color: Optional[str] = None,
) -> dict[str, Any]:
    """Update a tag.

    Args:
        id: The unique ID of the tag.
        color: Tag color in hex format (e.g. #FF0000).
    """
    params = UpdateTagParam(color=color)
    return await get_client().update_tag(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Delete Tag By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_tag_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a tag by ID.

    Args:
        id: The unique ID of the tag to delete.
    """
    return await get_client().delete_tag_by_id(id, get_user_token())

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Upsert Tags", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def upsert_tags(
    tags: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Upsert tags by name.

    Args:
        tags: List of tag names to upsert.
    """
    payload = {"tags": tags}
    data = await get_client().upsert_tags(payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Tag Assets", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def tag_assets(
    assetIds: list[str],
    tagIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Tag assets with specified tags.

    Args:
        assetIds: List of asset IDs.
        tagIds: List of tag IDs.
    """
    payload = {"assetIds": assetIds, "tagIds": tagIds}
    return await get_client().tag_assets(payload, get_user_token())

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Tag Assets By Tag", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def tag_assets_by_tag(
    id: str,
    assetIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Tag assets with a specific tag.

    Args:
        id: The tag ID.
        assetIds: List of asset IDs.
    """
    payload = {"ids": assetIds}
    data = await get_client().tag_assets_by_tag(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Untag Assets", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def untag_assets(
    id: str,
    assetIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Remove a tag from assets.

    Args:
        id: The tag ID.
        assetIds: List of asset IDs.
    """
    payload = {"ids": assetIds}
    data = await get_client().untag_assets(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

# =============================================================================
# People / Faces Tools
# =============================================================================

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="List All People", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_people(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List all people.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_all_people(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get Person By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_person_by_id(
id: str,
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get a single person by ID.

    Args:
        id: The unique ID of the person.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_person_by_id(
        id, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Create Person", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_person(
ctx: Context,
name: str = "",
birthDate: str = "",
color: str = "",
isFavorite: bool = False,
isHidden: bool = False,
) -> dict[str, Any]:
    """Create a new person.

    Args:
        name: Person name.
        birthDate: Person date of birth. ISO 8601 format (2026-06-22T15:00:00-04:00).
        color: Person color in hex format (e.g. #FF0000).
        isFavorite: True to mark as favorite.
        isHidden: True to hide person from People view.
    """
    params = CreatePersonParam(
        name=name, birthDate=birthDate, color=color,
        isFavorite=isFavorite, isHidden=isHidden,
    )
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    payload = {k: v for k, v in payload.items() if v not in ("", [])}
    return await get_client().create_person(
        payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Update Person", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_person(
id: str,
ctx: Context,
name: Optional[str] = None,
birthDate: Optional[str] = None,
color: Optional[str] = None,
isFavorite: Optional[bool] = None,
isHidden: Optional[bool] = None,
featureFaceAssetId: Optional[str] = None,
) -> dict[str, Any]:
    """Update a person.

    Args:
        id: The unique ID of the person.
        name: Person name.
        birthDate: Person date of birth. ISO 8601 format (2026-06-22T15:00:00-04:00).
        color: Person color in hex format (e.g. #FF0000).
        isFavorite: True to mark as favorite.
        isHidden: True to hide person from People view.
        featureFaceAssetId: Asset ID used for feature face thumbnail.
    """
    params = UpdatePersonParam(
        name=name, birthDate=birthDate, color=color,
        isFavorite=isFavorite, isHidden=isHidden,
        featureFaceAssetId=featureFaceAssetId,
    )
    return await get_client().update_person(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Delete Person By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_person_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a person by ID.

    Args:
        id: The unique ID of the person to delete.
    """
    return await get_client().delete_person_by_id(id, get_user_token())

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Merge People", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def merge_people(
    id: str,
    mergeIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Merge people into a single person.

    Args:
        id: The target person ID to keep.
        mergeIds: List of person IDs to merge into the target.
    """
    payload = {"ids": mergeIds}
    data = await get_client().merge_people(id, payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Person Statistics", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_person_statistics(
    id: str,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get statistics for a person.

    Args:
        id: The unique ID of the person.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_person_statistics(id, get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get Person Thumbnail Url", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_person_thumbnail_url(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get the URL for a person's thumbnail image.

    Args:
        id: The unique ID of the person.
    """
    url = await get_client().get_person_thumbnail_url(id, get_user_token())
    return {"url": url}

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List Faces By Asset", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_faces_by_asset(
    id: str,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get faces detected in an asset.

    Args:
        id: The unique ID of the asset.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_faces_by_asset(id, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Create Face", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_face(
    assetId: str,
    personId: str,
    x: int,
    y: int,
    width: int,
    height: int,
    imageWidth: int,
    imageHeight: int,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Create a face annotation on an asset.

    Args:
        assetId: The asset to attach the face to.
        personId: The person the face belongs to.
        x: Top-left X coordinate of the face bounding box.
        y: Top-left Y coordinate of the face bounding box.
        width: Width of the face bounding box.
        height: Height of the face bounding box.
        imageWidth: Full width of the source image.
        imageHeight: Full height of the source image.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    payload = {
        "assetId": assetId, "personId": personId,
        "x": x, "y": y, "width": width, "height": height,
        "imageWidth": imageWidth, "imageHeight": imageHeight,
    }
    data = await get_client().create_face(payload, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Reassign Face", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def reassign_face(
    assetId: str,
    personId: str,
    ctx: Context
) -> dict[str, Any]:
    """Reassign faces of an asset to a different person.

    Args:
        assetId: The asset ID containing faces.
        personId: The target person ID.
    """
    payload = {"data": [{"assetId": assetId, "personId": personId}]}
    data = await get_client().reassign_faces(personId, payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)
    return {"results": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Delete Face", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_face(
    id: str,
    ctx: Context,
    force: bool = True,
) -> dict[str, Any]:
    """Delete a face.

    Args:
        id: The face ID to delete.
        force: Force deletion even if person has other faces. Defaults to True.
    """
    payload = {"force": force}
    return await get_client().delete_face(id, payload, get_user_token())

# =============================================================================
# Library Tools
# =============================================================================

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="List All Libraries", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_libraries(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List all libraries.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_all_libraries(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Library By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_library_by_id(
id: str,
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get a single library by ID.

    Args:
        id: The unique ID of the library.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_library_by_id(
        id, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Create Library", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_library(
ownerId: str,
ctx: Context,
name: str = "",
importPaths: list[str] = [],
exclusionPatterns: list[str] = [],
) -> dict[str, Any]:
    """Create a new library.

    Args:
        ownerId: Owner user ID.
        name: Library name.
        importPaths: List of import paths.
        exclusionPatterns: List of exclusion patterns.
    """
    params = CreateLibraryParam(ownerId=ownerId, name=name)
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    if importPaths:
        payload["importPaths"] = importPaths
    if exclusionPatterns:
        payload["exclusionPatterns"] = exclusionPatterns
    return await get_client().create_library(payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Update Library", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_library(
id: str,
ctx: Context,
name: Optional[str] = None,
importPaths: Optional[list[str]] = None,
exclusionPatterns: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Update a library.

    Args:
        id: The unique ID of the library.
        name: Library name.
        importPaths: List of import paths.
        exclusionPatterns: List of exclusion patterns.
    """
    params = UpdateLibraryParam(name=name)
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    if importPaths is not None:
        payload["importPaths"] = importPaths
    if exclusionPatterns is not None:
        payload["exclusionPatterns"] = exclusionPatterns
    return await get_client().update_library(id, payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Delete Library By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_library_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a library by ID.

    Args:
        id: The unique ID of the library to delete.
    """
    return await get_client().delete_library_by_id(id, get_user_token())

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Run Job", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def run_job(
    jobId: str,
    ctx: Context
) -> dict[str, Any]:
    """Run a background job once (e.g. duplicateDetection).

    Args:
        jobId: The name of the job to run.
    """
    return await get_client().run_job(jobId, get_user_token())

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Scan Library", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def scan_library(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Scan a library for new files.

    Args:
        id: The unique ID of the library.
    """
    return await get_client().scan_library(id, get_user_token())

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Library Statistics", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_library_statistics(
    id: str,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get statistics for a library.

    Args:
        id: The unique ID of the library.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_library_statistics(id, get_user_token(), include_all_fields=include_all_fields)

# =============================================================================
# Memory Tools
# =============================================================================

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List All Memories", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_memories(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List all memories.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_all_memories(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get Memory By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_memory_by_id(
id: str,
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get a single memory by ID.

    Args:
        id: The unique ID of the memory.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_memory_by_id(
        id, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Create Memory", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_memory(
memoryAt: str,
year: int,
ctx: Context,
assetIds: list[str] = [],
isSaved: bool = False,
hideAt: str = "",
showAt: str = "",
seenAt: str = "",
) -> dict[str, Any]:
    """Create a new memory.

    Args:
        memoryAt: Memory date. ISO 8601 format (2026-06-22T15:00:00-04:00).
        year: Year for the on_this_day memory.
        assetIds: List of asset IDs.
        isSaved: True to save memory.
        hideAt: Date when memory should be hidden. ISO 8601 format (2026-06-22T15:00:00-04:00).
        showAt: Date when memory should be shown. ISO 8601 format (2026-06-22T15:00:00-04:00).
        seenAt: Date when memory was seen. ISO 8601 format (2026-06-22T15:00:00-04:00).
    """
    payload = {
        "type": "on_this_day",
        "memoryAt": _normalize_datetime(memoryAt),
        "data": {"year": year},
    }
    if assetIds:
        payload["assetIds"] = assetIds
    if isSaved:
        payload["isSaved"] = True
    if hideAt:
        payload["hideAt"] = _normalize_datetime(hideAt)
    if showAt:
        payload["showAt"] = _normalize_datetime(showAt)
    if seenAt:
        payload["seenAt"] = _normalize_datetime(seenAt)
    return await get_client().create_memory(payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Update Memory", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_memory(
id: str,
ctx: Context,
isSaved: Optional[bool] = None,
memoryAt: Optional[str] = None,
seenAt: Optional[str] = None,
) -> dict[str, Any]:
    """Update a memory.

    Args:
        id: The unique ID of the memory.
        isSaved: True to save memory.
        memoryAt: Memory date. ISO 8601 format (2026-06-22T15:00:00-04:00).
        seenAt: Date when memory was seen. ISO 8601 format (2026-06-22T15:00:00-04:00).
    """
    params = UpdateMemoryParam(isSaved=isSaved, memoryAt=memoryAt, seenAt=seenAt)
    return await get_client().update_memory(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Delete Memory By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_memory_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a memory by ID.

    Args:
        id: The unique ID of the memory to delete.
    """
    return await get_client().delete_memory_by_id(id, get_user_token())

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Add Assets To Memory", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def add_assets_to_memory(
    id: str,
    assetIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Add assets to a memory.

    Args:
        id: The unique ID of the memory.
        assetIds: List of asset IDs.
    """
    payload = {"ids": assetIds}
    data = await get_client().add_assets_to_memory(id, payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Remove Assets From Memory", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def remove_assets_from_memory(
    id: str,
    assetIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Remove assets from a memory.

    Args:
        id: The unique ID of the memory.
        assetIds: List of asset IDs to remove.
    """
    payload = {"ids": assetIds}
    data = await get_client().remove_assets_from_memory(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Memory Statistics", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_memory_statistics(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get memory statistics.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_memory_statistics(get_user_token(), include_all_fields=include_all_fields)

# =============================================================================
# Stack Tools
# =============================================================================

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="List All Stacks", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_stacks(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List all stacks.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_all_stacks(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Stack By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_stack_by_id(
id: str,
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get a single stack by ID.

    Args:
        id: The unique ID of the stack.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_stack_by_id(
        id, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Create Stack", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_stack(
    assetIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Create a stack from assets (minimum 2 assets).

    Args:
        assetIds: List of asset IDs. First becomes primary (required, min 2).
    """
    payload = {"assetIds": assetIds}
    return await get_client().create_stack(payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Update Stack", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_stack(
id: str,
ctx: Context,
primaryAssetId: Optional[str] = None,
) -> dict[str, Any]:
    """Update a stack.

    Args:
        id: The unique ID of the stack.
        primaryAssetId: Asset ID to set as primary.
    """
    params = UpdateStackParam(primaryAssetId=primaryAssetId)
    return await get_client().update_stack(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Delete Stack By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_stack_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a stack by ID.

    Args:
        id: The unique ID of the stack to delete.
    """
    return await get_client().delete_stack_by_id(id, get_user_token())

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Remove Asset From Stack", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def remove_asset_from_stack(
    id: str,
    assetId: str,
    ctx: Context
) -> dict[str, Any]:
    """Remove an asset from a stack.

    Args:
        id: The unique ID of the stack.
        assetId: The asset ID to remove.
    """
    return await get_client().remove_asset_from_stack(id, assetId, get_user_token())

# =============================================================================
# Shared Link Tools
# =============================================================================

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List All Shared Links", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_shared_links(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List all shared links.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_all_shared_links(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get Shared Link By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_shared_link_by_id(
id: str,
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get a single shared link by ID.

    Args:
        id: The unique ID of the shared link.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_shared_link_by_id(
        id, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Create Shared Link", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_shared_link(
type: str,
ctx: Context,
    assetIds: list[str] = [],
    albumId: str = "",
description: str = "",
expiresAt: str = "",
password: str = "",
allowDownload: bool = True,
allowUpload: bool = False,
showMetadata: bool = True,
slug: str = "",
) -> dict[str, Any]:
    """Create a new shared link.

    Args:
        type: ALBUM or INDIVIDUAL.
        assetIds: List of asset IDs (for INDIVIDUAL type).
        albumId: Album ID (for ALBUM type).
        description: Link description.
        expiresAt: Expiration date. ISO 8601 format (2026-06-22T15:00:00-04:00).
        password: Link password.
        allowDownload: Allow downloads. Defaults to True.
        allowUpload: Allow uploads. Defaults to False.
        showMetadata: Show metadata. Defaults to True.
        slug: Custom URL slug.
    """
    params = CreateSharedLinkParam(
        type=type, description=description, expiresAt=expiresAt,
        password=password, allowDownload=allowDownload,
        allowUpload=allowUpload, showMetadata=showMetadata, slug=slug,
    )
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    payload = {k: v for k, v in payload.items() if v != ""}
    if assetIds:
        payload["assetIds"] = assetIds
    if albumId:
        payload["albumId"] = albumId
    return await get_client().create_shared_link(payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Update Shared Link", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_shared_link(
id: str,
ctx: Context,
description: Optional[str] = None,
expiresAt: Optional[str] = None,
password: Optional[str] = None,
allowDownload: Optional[bool] = None,
allowUpload: Optional[bool] = None,
showMetadata: Optional[bool] = None,
slug: Optional[str] = None,
) -> dict[str, Any]:
    """Update a shared link.

    Args:
        id: The unique ID of the shared link.
        description: Link description.
        expiresAt: Expiration date. ISO 8601 format (2026-06-22T15:00:00-04:00).
        password: Link password.
        allowDownload: Allow downloads.
        allowUpload: Allow uploads.
        showMetadata: Show metadata.
        slug: Custom URL slug.
    """
    params = UpdateSharedLinkParam(
        description=description, expiresAt=expiresAt, password=password,
        allowDownload=allowDownload, allowUpload=allowUpload,
        showMetadata=showMetadata, slug=slug,
    )
    return await get_client().update_shared_link(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Delete Shared Link By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_shared_link_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a shared link by ID.

    Args:
        id: The unique ID of the shared link to delete.
    """
    return await get_client().delete_shared_link_by_id(id, get_user_token())

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Add Assets To Shared Link", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def add_assets_to_shared_link(
    id: str,
    assetIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Add assets to a shared link.

    Args:
        id: The unique ID of the shared link.
        assetIds: List of asset IDs to add.
    """
    payload = {"assetIds": assetIds}
    data = await get_client().add_assets_to_shared_link(id, payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Remove Assets From Shared Link", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def remove_assets_from_shared_link(
    id: str,
    assetIds: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Remove assets from a shared link.

    Args:
        id: The unique ID of the shared link.
        assetIds: List of asset IDs to remove.
    """
    payload = {"assetIds": assetIds}
    data = await get_client().remove_assets_from_shared_link(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

# =============================================================================
# Activity Tools
# =============================================================================

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List All Activities", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_activities(
ctx: Context,
albumId: str = "",
assetId: str = "",
type: str = "",
level: str = "",
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List activities.

    Args:
        albumId: Filter by album ID.
        assetId: Filter by asset ID.
        type: Filter by reaction type (like, comment).
        level: Filter by reaction level: album or asset.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    params = {}
    if albumId:
        params["albumId"] = albumId
    if assetId:
        params["assetId"] = assetId
    if type:
        params["type"] = type
    if level:
        params["level"] = level
    data = await get_client().get_all_activities(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        params=params or None,
    )
    return {"items": json_to_toon(data)} if isinstance(data, list) else data

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Activity Statistics", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_activity_statistics(
albumId: str,
ctx: Context,
assetId: str = "",
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get activity statistics for an album.

    Args:
        albumId: Album ID.
        assetId: Asset ID.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    params = {"albumId": albumId}
    if assetId:
        params["assetId"] = assetId
    return await get_client().get_activity_statistics(get_user_token(), params=params, include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Create Activity", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_activity(
albumId: str,
type: str,
ctx: Context,
assetId: str = "",
comment: str = "",
) -> dict[str, Any]:
    """Create an activity (like or comment).

    Args:
        albumId: Album ID.
        type: Activity type (like, comment).
        assetId: Asset ID (for per-asset activity).
        comment: Comment text (required if type is comment).
    """
    payload = {"albumId": albumId, "type": type}
    if assetId:
        payload["assetId"] = assetId
    if comment:
        payload["comment"] = comment
    return await get_client().create_activity(payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Delete Activity By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_activity_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete an activity by ID.

    Args:
        id: The unique ID of the activity to delete.
    """
    return await get_client().delete_activity_by_id(id, get_user_token())

# =============================================================================
# Partner Tools
# =============================================================================

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List All Partners", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_partners(
ctx: Context,
direction: str = "",
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List partners.

    Args:
        direction: Filter direction (shared-with or shared-by).
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    params = {}
    if direction:
        params["direction"] = direction
    data = await get_client().get_all_partners(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        params=params or None,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Create Partner", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_partner(
    sharedWithId: str,
    ctx: Context
) -> dict[str, Any]:
    """Add a partner to share libraries.

    Args:
        sharedWithId: User ID to share with.
    """
    params = CreatePartnerParam(sharedWithId=sharedWithId)
    return await get_client().create_partner(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Update Partner", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_partner(
    id: str,
    inTimeline: bool,
    ctx: Context
) -> dict[str, Any]:
    """Update a partner's timeline visibility.

    Args:
        id: Partner (user) ID.
        inTimeline: True to show partner assets in your timeline.
    """
    params = UpdatePartnerParam(inTimeline=inTimeline)
    return await get_client().update_partner(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Delete Partner By Id", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_partner_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Remove a partner.

    Args:
        id: Partner (user) ID to remove.
    """
    return await get_client().delete_partner_by_id(id, get_user_token())

# =============================================================================
# Search Tools
# =============================================================================

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Search Metadata", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def search_metadata(
ctx: Context,
page: int = 1,
size: int = 50,
query: Optional[str] = None,
type: Optional[str] = None,
isFavorite: Optional[bool] = None,
isMotion: Optional[bool] = None,
isOffline: Optional[bool] = None,
isNotInAlbum: Optional[bool] = None,
takenAfter: Optional[str] = None,
takenBefore: Optional[str] = None,
originalFileName: Optional[str] = None,
city: Optional[str] = None,
state: Optional[str] = None,
country: Optional[str] = None,
make: Optional[str] = None,
model: Optional[str] = None,
    personIds: list[str] = [],
    tagIds: list[str] = [],
    albumIds: list[str] = [],
    libraryId: Optional[str] = None,
    order: Optional[str] = None,
    withExif: bool = False,
    withPeople: bool = False,
    withStacked: bool = False,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Search assets by metadata fields.

    Args:
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 50.
        query: General search query.
        type: IMAGE, VIDEO, AUDIO, or OTHER.
        isFavorite: Filter by favorite status.
        isMotion: Filter by motion photo.
        isOffline: Filter by offline status.
        isNotInAlbum: Filter assets not in any album.
        takenAfter: Filter by taken date after. ISO 8601 format (2026-06-22T15:00:00-04:00).
        takenBefore: Filter by taken date before. ISO 8601 format (2026-06-22T15:00:00-04:00).
        originalFileName: Filter by original file name.
        city: Filter by city name.
        state: Filter by state/province name.
        country: Filter by country name.
        make: Filter by camera make.
        model: Filter by camera model.
        personIds: List of person IDs.
        tagIds: List of tag IDs.
        albumIds: List of album IDs.
        libraryId: Library ID to filter by.
        order: asc or desc.
        withExif: Include EXIF data.
        withPeople: Include people data.
        withStacked: Include stacked assets.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    payload = {"page": page, "size": size}
    if query: payload["query"] = query
    if type: payload["type"] = type
    if isFavorite is not None: payload["isFavorite"] = isFavorite
    if isMotion is not None: payload["isMotion"] = isMotion
    if isOffline is not None: payload["isOffline"] = isOffline
    if isNotInAlbum is not None: payload["isNotInAlbum"] = isNotInAlbum
    if takenAfter: payload["takenAfter"] = _normalize_datetime(takenAfter)
    if takenBefore: payload["takenBefore"] = _normalize_datetime(takenBefore)
    if originalFileName: payload["originalFileName"] = originalFileName
    if city: payload["city"] = city
    if state: payload["state"] = state
    if country: payload["country"] = country
    if make: payload["make"] = make
    if model: payload["model"] = model
    if personIds: payload["personIds"] = personIds
    if tagIds: payload["tagIds"] = tagIds
    if albumIds: payload["albumIds"] = albumIds
    if libraryId: payload["libraryId"] = libraryId
    if order: payload["order"] = order
    if withExif: payload["withExif"] = True
    if withPeople: payload["withPeople"] = True
    if withStacked: payload["withStacked"] = True
    return await get_client().search_metadata(payload, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Search Smart", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def search_smart(
query: str,
ctx: Context,
page: int = 1,
size: int = 50,
include_all_fields: bool = False,
type: Optional[str] = None,
isFavorite: Optional[bool] = None,
city: Optional[str] = None,
state: Optional[str] = None,
country: Optional[str] = None,
make: Optional[str] = None,
model: Optional[str] = None,
    personIds: list[str] = [],
    tagIds: list[str] = [],
    albumIds: list[str] = [],
    libraryId: Optional[str] = None,
) -> dict[str, Any]:
    """Search assets using natural language (CLIP-based smart search).

    Args:
        query: Natural language search query.
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 50.
        include_all_fields: Default False (common fields only). Set True for all fields.
        type: Asset type: IMAGE, VIDEO, AUDIO, or OTHER.
        isFavorite: Filter by favorite.
        city: Filter by city.
        state: Filter by state.
        country: Filter by country.
        make: Filter by camera make (e.g. Canon, Apple).
        model: Filter by camera model (e.g. EOS R5, iPhone 15).
        personIds: List of person IDs.
        tagIds: List of tag IDs.
        albumIds: List of album IDs.
        libraryId: Library ID.
    """
    payload = {"query": query, "page": page, "size": size}
    if type: payload["type"] = type
    if isFavorite is not None: payload["isFavorite"] = isFavorite
    if city: payload["city"] = city
    if state: payload["state"] = state
    if country: payload["country"] = country
    if make: payload["make"] = make
    if model: payload["model"] = model
    if personIds: payload["personIds"] = personIds
    if tagIds: payload["tagIds"] = tagIds
    if albumIds: payload["albumIds"] = albumIds
    if libraryId: payload["libraryId"] = libraryId
    return await get_client().search_smart(payload, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Search Suggestions", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def search_suggestions(
    type: str,
    query: str,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get search suggestions.

    Args:
        type: Suggestion type (country, state, city, camera-make, camera-model, camera-lens-model).
        query: Search query text.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    params = {"type": type, "query": query}
    result = await get_client().search_suggestions(params, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Search Explore", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def search_explore(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get explore data grouped by city.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    result = await get_client().search_explore(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Search Cities", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def search_cities(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get assets grouped by city.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    result = await get_client().search_cities(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Search Random", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def search_random(
    ctx: Context,
    size: int = 100,
    include_all_fields: bool = False,
    type: Optional[str] = None,
    isFavorite: Optional[bool] = None,
    isMotion: Optional[bool] = None,
    isNotInAlbum: Optional[bool] = None,
    personIds: list[str] = [],
    tagIds: list[str] = [],
    albumIds: list[str] = [],
    libraryId: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
) -> dict[str, Any]:
    """Get a random selection of assets.

    Args:
        size: Number of results to return. Defaults to 100.
        include_all_fields: Default False (common fields only). Set True for all fields.
        type: IMAGE, VIDEO, AUDIO, or OTHER.
        isFavorite: Filter by favorite status.
        isMotion: Filter by motion photo.
        isNotInAlbum: Filter assets not in any album.
        personIds: List of person IDs.
        tagIds: List of tag IDs.
        albumIds: List of album IDs.
        libraryId: Library ID.
        city: Filter by city name.
        state: Filter by state/province name.
        country: Filter by country name.
        make: Filter by camera make (e.g. Canon, Apple).
        model: Filter by camera model (e.g. EOS R5, iPhone 15).
    """
    payload: dict[str, Any] = {"size": size}
    if type: payload["type"] = type
    if isFavorite is not None: payload["isFavorite"] = isFavorite
    if isMotion is not None: payload["isMotion"] = isMotion
    if isNotInAlbum is not None: payload["isNotInAlbum"] = isNotInAlbum
    if personIds: payload["personIds"] = personIds
    if tagIds: payload["tagIds"] = tagIds
    if albumIds: payload["albumIds"] = albumIds
    if libraryId: payload["libraryId"] = libraryId
    if city: payload["city"] = city
    if state: payload["state"] = state
    if country: payload["country"] = country
    if make: payload["make"] = make
    if model: payload["model"] = model
    data = await get_client().search_random(payload, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": data} if isinstance(data, list) else data

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Search Person", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def search_person(
    ctx: Context,
    name: str,
    withHidden: bool = False,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Search for people by name.

    Args:
        name: Person name to search for.
        withHidden: Include hidden people.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    params = {"name": name, "withHidden": withHidden}
    result = await get_client().search_person(params, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Search Places", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def search_places(
    ctx: Context,
    name: str,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Search for places by name.

    Args:
        name: Place name to search for.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    params = {"name": name}
    result = await get_client().search_places(params, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List Assets By People", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_assets_by_people(
    ctx: Context,
    personIds: list[str],
    page: int = 1,
    size: int = 100,
    include_all_fields: bool = False,
    type: Optional[str] = None,
    isFavorite: Optional[bool] = None,
) -> dict[str, Any]:
    """List assets for specific people.

    Args:
        personIds: List of person IDs.
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 100.
        include_all_fields: Default False (common fields only). Set True for all fields.
        type: IMAGE, VIDEO, AUDIO, or OTHER.
        isFavorite: Filter by favorite status.
    """
    payload: dict[str, Any] = {"page": page, "size": size}
    if personIds:
        payload["personIds"] = personIds
    if type: payload["type"] = type
    if isFavorite is not None: payload["isFavorite"] = isFavorite
    return await get_client().search_metadata(
        payload, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )

# =============================================================================
# Timeline & Map Tools
# =============================================================================

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="List Time Buckets", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_time_buckets(
size: str,
ctx: Context,
albumId: str = "",
personId: str = "",
userId: str = "",
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get time buckets for timeline view.

    Args:
        size: Bucket size (MONTH, DAY).
        albumId: Filter by album.
        personId: Filter by person.
        userId: Filter by user.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    params = {"size": size.upper() if size else "MONTH"}
    if albumId: params["albumId"] = albumId
    if personId: params["personId"] = personId
    if userId: params["userId"] = userId
    result = await get_client().get_time_buckets(params, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="List Time Bucket Assets", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_time_bucket_assets(
size: str,
timeBucket: str,
ctx: Context,
albumId: str = "",
personId: str = "",
userId: str = "",
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get assets in a specific time bucket.

    Args:
        size: Bucket size (MONTH, DAY).
        timeBucket: The time bucket key from list_time_buckets.
        albumId: Filter by album.
        personId: Filter by person.
        userId: Filter by user.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    params = {"size": size.upper() if size else "MONTH", "timeBucket": timeBucket}
    if albumId: params["albumId"] = albumId
    if personId: params["personId"] = personId
    if userId: params["userId"] = userId
    data = await get_client().get_time_bucket(params, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List Map Markers", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_map_markers(
ctx: Context,
fileCreatedAfter: str = "",
fileCreatedBefore: str = "",
albumId: str = "",
personId: str = "",
withPartners: bool = False,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get map markers for assets with geolocation data.

    Args:
        fileCreatedAfter: Filter by file creation date after. ISO 8601 format (2026-06-22T15:00:00-04:00).
        fileCreatedBefore: Filter by file creation date before. ISO 8601 format (2026-06-22T15:00:00-04:00).
        albumId: Filter by album ID.
        personId: Filter by person ID.
        withPartners: Include partner assets.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    params = {}
    if fileCreatedAfter: params["fileCreatedAfter"] = fileCreatedAfter
    if fileCreatedBefore: params["fileCreatedBefore"] = fileCreatedBefore
    if albumId: params["albumId"] = albumId
    if personId: params["personId"] = personId
    if withPartners: params["withPartners"] = "true"
    result = await get_client().get_map_markers(params, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Reverse Geocode", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def reverse_geocode(
    lat: float,
    lon: float,
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Reverse geocode coordinates to a location.

    Args:
        lat: Latitude.
        lon: Longitude.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    params = {"lat": lat, "lon": lon}
    result = await get_client().reverse_geocode(params, get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)
    return {"results": result} if isinstance(result, list) else result

# =============================================================================
# Duplicate Tools
# =============================================================================

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List All Duplicates", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_duplicates(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List all duplicate groups.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_all_duplicates(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Dismiss Duplicate Group", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def dismiss_duplicate_group(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Dismiss a duplicate group.

    Args:
        id: Duplicate group ID to dismiss.
    """
    return await get_client().dismiss_duplicate_group(id, get_user_token())

# =============================================================================
# Trash Tools
# =============================================================================

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Empty Trash", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def empty_trash(ctx: Context) -> dict[str, Any]:
    """Permanently empty the trash."""
    return await get_client().empty_trash(get_user_token())

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Restore Trash", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def restore_trash(ctx: Context) -> dict[str, Any]:
    """Restore all trashed assets."""
    return await get_client().restore_trash(get_user_token())

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Restore Trash Assets", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def restore_trash_assets(
    ids: list[str],
    ctx: Context
) -> dict[str, Any]:
    """Restore specific trashed assets.

    Args:
        ids: List of asset IDs to restore.
    """
    payload = {"ids": ids}
    return await get_client().restore_trash_assets(payload, get_user_token())

# =============================================================================
# System Config Tools
# =============================================================================

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get System Config", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_system_config(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get the full system configuration.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_system_config(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get System Config Defaults", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_system_config_defaults(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get system configuration defaults.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_system_config_defaults(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Get Storage Template Options", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_storage_template_options(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get available storage template options.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_storage_template_options(get_user_token(), include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False)

# =============================================================================
# User & Account Tools
# =============================================================================

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="List All Users", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def list_all_users(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List all users.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    data = await get_client().get_all_users(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get User By Id", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_user_by_id(
id: str,
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get a single user by ID.

    Args:
        id: The unique user ID.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_user_by_id(
        id, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"basic", "immich"}, annotations=ToolAnnotations(title="Get My User Info", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_my_user_info(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get the current authenticated user's info.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_my_user_info(
        get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Update My User", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_my_user(
ctx: Context,
email: Optional[str] = None,
name: Optional[str] = None,
password: Optional[str] = None,
avatarColor: Optional[str] = None,
) -> dict[str, Any]:
    """Update the current user's profile.

    Args:
        email: New email address.
        name: New display name.
        password: New password (deprecated, use change password endpoint).
        avatarColor: Avatar color: primary, pink, red, yellow, blue, green, purple, orange, gray, or amber.
    """
    params = UpdateMyUserParam(
        email=email, name=name, password=password, avatarColor=avatarColor,
    )
    return await get_client().update_my_user(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE
    )

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get My Preferences", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_my_preferences(
    ctx: Context,
    include_all_fields: bool = False,
) -> dict[str, Any]:
    """Get the current user's preferences.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_my_preferences(get_user_token(), include_all_fields=include_all_fields)

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Update My Preferences", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def update_my_preferences(
    ctx: Context,
    albums_defaultAssetOrder: Optional[str] = None,
    avatar_color: Optional[str] = None,
    cast_gCastEnabled: Optional[bool] = None,
    download_archiveSize: Optional[int] = None,
    download_includeEmbeddedVideos: Optional[bool] = None,
    emailNotifications_enabled: Optional[bool] = None,
    emailNotifications_albumInvite: Optional[bool] = None,
    emailNotifications_albumUpdate: Optional[bool] = None,
    folders_enabled: Optional[bool] = None,
    folders_sidebarWeb: Optional[bool] = None,
    memories_enabled: Optional[bool] = None,
    memories_duration: Optional[int] = None,
    people_enabled: Optional[bool] = None,
    people_sidebarWeb: Optional[bool] = None,
    people_minimumFaces: Optional[int] = None,
    purchase_showSupportBadge: Optional[bool] = None,
    purchase_hideBuyButtonUntil: Optional[str] = None,
    ratings_enabled: Optional[bool] = None,
    sharedLinks_enabled: Optional[bool] = None,
    sharedLinks_sidebarWeb: Optional[bool] = None,
    tags_enabled: Optional[bool] = None,
    tags_sidebarWeb: Optional[bool] = None,
) -> dict[str, Any]:
    """Update the current user's preferences.

    All parameters are optional — only include the ones you want to change.
    Parameters are grouped by category using underscore prefixes.

    Args:
        albums_defaultAssetOrder: asc or desc.
        avatar_color: Avatar color. One of: 'primary', 'pink', 'red', 'yellow',
            'blue', 'green', 'purple', 'orange', 'gray', 'amber'.
        cast_gCastEnabled: Enable Google Cast support.
        download_archiveSize: Download archive size limit in bytes.
        download_includeEmbeddedVideos: Include embedded videos in downloads.
        emailNotifications_enabled: Enable email notifications.
        emailNotifications_albumInvite: Notify on album invite.
        emailNotifications_albumUpdate: Notify on album update.
        folders_enabled: Enable folder views.
        folders_sidebarWeb: Show folders in web sidebar.
        memories_enabled: Enable memories feature.
        memories_duration: Memory display duration in seconds.
        people_enabled: Enable people/facial recognition.
        people_sidebarWeb: Show people in web sidebar.
        people_minimumFaces: Minimum number of faces to show a person.
        purchase_showSupportBadge: Show support badge.
        purchase_hideBuyButtonUntil: Hide purchase button until date. ISO 8601 format (2026-06-22T15:00:00-04:00).
        ratings_enabled: Enable star ratings.
        sharedLinks_enabled: Enable shared links.
        sharedLinks_sidebarWeb: Show shared links in web sidebar.
        tags_enabled: Enable tags.
        tags_sidebarWeb: Show tags in web sidebar.
    """
    payload = {}
    if albums_defaultAssetOrder is not None:
        payload["albums"] = {"defaultAssetOrder": albums_defaultAssetOrder}
    if avatar_color is not None:
        payload["avatar"] = {"color": avatar_color}
    if cast_gCastEnabled is not None:
        payload["cast"] = {"gCastEnabled": cast_gCastEnabled}
    if download_archiveSize is not None or download_includeEmbeddedVideos is not None:
        d = {}
        if download_archiveSize is not None:
            d["archiveSize"] = download_archiveSize
        if download_includeEmbeddedVideos is not None:
            d["includeEmbeddedVideos"] = download_includeEmbeddedVideos
        payload["download"] = d
    if emailNotifications_enabled is not None or emailNotifications_albumInvite is not None or emailNotifications_albumUpdate is not None:
        e = {}
        if emailNotifications_enabled is not None:
            e["enabled"] = emailNotifications_enabled
        if emailNotifications_albumInvite is not None:
            e["albumInvite"] = emailNotifications_albumInvite
        if emailNotifications_albumUpdate is not None:
            e["albumUpdate"] = emailNotifications_albumUpdate
        payload["emailNotifications"] = e
    if folders_enabled is not None or folders_sidebarWeb is not None:
        f = {}
        if folders_enabled is not None:
            f["enabled"] = folders_enabled
        if folders_sidebarWeb is not None:
            f["sidebarWeb"] = folders_sidebarWeb
        payload["folders"] = f
    if memories_enabled is not None or memories_duration is not None:
        m = {}
        if memories_enabled is not None:
            m["enabled"] = memories_enabled
        if memories_duration is not None:
            m["duration"] = memories_duration
        payload["memories"] = m
    if people_enabled is not None or people_sidebarWeb is not None or people_minimumFaces is not None:
        p = {}
        if people_enabled is not None:
            p["enabled"] = people_enabled
        if people_sidebarWeb is not None:
            p["sidebarWeb"] = people_sidebarWeb
        if people_minimumFaces is not None:
            p["minimumFaces"] = people_minimumFaces
        payload["people"] = p
    if purchase_showSupportBadge is not None or purchase_hideBuyButtonUntil is not None:
        pu = {}
        if purchase_showSupportBadge is not None:
            pu["showSupportBadge"] = purchase_showSupportBadge
        if purchase_hideBuyButtonUntil is not None:
            pu["hideBuyButtonUntil"] = purchase_hideBuyButtonUntil
        payload["purchase"] = pu
    if ratings_enabled is not None:
        payload["ratings"] = {"enabled": ratings_enabled}
    if sharedLinks_enabled is not None or sharedLinks_sidebarWeb is not None:
        sl = {}
        if sharedLinks_enabled is not None:
            sl["enabled"] = sharedLinks_enabled
        if sharedLinks_sidebarWeb is not None:
            sl["sidebarWeb"] = sharedLinks_sidebarWeb
        payload["sharedLinks"] = sl
    if tags_enabled is not None or tags_sidebarWeb is not None:
        t = {}
        if tags_enabled is not None:
            t["enabled"] = tags_enabled
        if tags_sidebarWeb is not None:
            t["sidebarWeb"] = tags_sidebarWeb
        payload["tags"] = t
    return await get_client().update_my_preferences(payload, get_user_token())

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Get User Profile Image Url", readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def get_user_profile_image_url(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get the URL for a user's profile image.

    Args:
        id: The user ID.
    """
    url = await get_client().get_user_profile_image_url(id, get_user_token())
    return {"url": url}

@mcp.tool(
    tags={"primary", "immich"}, annotations=ToolAnnotations(title="Delete My Onboarding", readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
)
async def delete_my_onboarding(ctx: Context) -> dict[str, Any]:
    """Delete the current user's onboarding status."""
    return await get_client().delete_my_onboarding(get_user_token())

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Create User", readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
async def create_user(
    email: str,
    password: str,
    name: str,
    ctx: Context,
    storageLabel: Optional[str] = None,
    quotaSizeInBytes: Optional[int] = None,
) -> dict[str, Any]:
    """Create a new user (admin only).

    Args:
        email: User email address.
        password: User password.
        name: User display name.
        storageLabel: Optional storage label.
        quotaSizeInBytes: Optional quota in bytes.
    """
    payload: dict[str, Any] = {
        "email": email,
        "password": password,
        "name": name,
    }
    if storageLabel is not None:
        payload["storageLabel"] = storageLabel
    if quotaSizeInBytes is not None:
        payload["quotaSizeInBytes"] = quotaSizeInBytes
    return await get_client().create_user(payload, get_user_token(), include_all_fields=ALLOW_ALL_AGGREGATE)

@mcp.tool(
    tags={"advanced", "immich"}, annotations=ToolAnnotations(title="Delete User", readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
)
async def delete_user(
    id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Delete a user by ID (admin only).

    Args:
        id: The user ID to delete.
    """
    return await get_client().delete_user(id, get_user_token())

# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Run the Immich MCP server."""
    if not os.getenv("IMMICH_BASE_URL"):
        print("ERROR: IMMICH_BASE_URL environment variable is required", file=sys.stderr)
        print("Example: export IMMICH_BASE_URL=http://immich-api:80", file=sys.stderr)
        sys.exit(1)

    port_env = os.getenv("MCP_SERVER_PORT")
    if not port_env:
        print("ERROR: MCP_SERVER_PORT environment variable is required", file=sys.stderr)
        print("Example: export MCP_SERVER_PORT=6042", file=sys.stderr)
        sys.exit(1)

    host = "0.0.0.0"
    port = int(port_env)
    path = "/mcp"
    if IS_STATEFUL:
        app = mcp.http_app(path=path, json_response=True)
    else:
        app = mcp.http_app(path=path, json_response=True, stateless_http=True)
    app = AuthMiddleware(app)
    print(f"Starting Immich MCP server on http://{host}:{port}{path}")
    import uvicorn
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
