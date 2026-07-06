import json
import os
import sys
from contextvars import ContextVar
from typing import Any, Optional, Union

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from toon_mcp import json_to_toon

from .client import ImmichClient

_current_user_token: ContextVar[Optional[str]] = ContextVar("current_user_token", default=None)

ALLOW_ALL_AGGREGATE = os.getenv("ALLOW_ALL_AGGREGATE", "false").lower() in ("true", "1", "yes")


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
        return parsed.strftime('%Y-%m-%d %H:%M:%S')
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
    angle: float = Field(description="Rotation angle. Must be 0, 90, 180, or 270.")


class MirrorParameters(BaseModel):
    axis: str = Field(description="Mirror axis. 'horizontal' or 'vertical'.")


class AssetEditItem(BaseModel):
    action: str = Field(description="Edit action. One of: 'crop', 'rotate', 'mirror'.")
    parameters: Union[CropParameters, RotateParameters, MirrorParameters] = Field(
        description="Parameters for the edit action. Use the matching parameters type for the chosen action."
    )


# Preferences are passed as flat parameters in update_my_preferences

# =============================================================================
# Server Tools
# =============================================================================

@mcp.tool()
async def get_server_ping(ctx: Context) -> dict[str, Any]:
    """Check if the Immich server is reachable."""
    return await get_client().get_server_ping(get_user_token())

@mcp.tool(tags={"read"})
async def get_server_version(ctx: Context) -> dict[str, Any]:
    """Get the Immich server version."""
    return await get_client().get_server_version(get_user_token())

@mcp.tool(tags={"immich"})
async def get_server_about(ctx: Context) -> dict[str, Any]:
    """Get general server information."""
    return await get_client().get_server_about(get_user_token())

@mcp.tool(tags={"read", "basic", "immich"})
async def get_server_config(ctx: Context) -> dict[str, Any]:
    """Get the server configuration settings."""
    return await get_client().get_server_config(get_user_token())

@mcp.tool(tags={"read", "primary", "immich"})
async def get_server_features(ctx: Context) -> dict[str, Any]:
    """Get the server feature flags."""
    return await get_client().get_server_features(get_user_token())

@mcp.tool(tags={"read", "primary", "immich"})
async def get_server_statistics(ctx: Context) -> dict[str, Any]:
    """Get server usage statistics."""
    return await get_client().get_server_statistics(get_user_token())

@mcp.tool(tags={"read", "primary", "immich"})
async def get_server_storage(ctx: Context) -> dict[str, Any]:
    """Get server storage information."""
    return await get_client().get_server_storage(get_user_token())

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_server_media_types(ctx: Context) -> dict[str, Any]:
    """Get supported media types."""
    return await get_client().get_server_media_types(get_user_token())

@mcp.tool(tags={"read", "basic", "immich"})
async def get_server_version_check(ctx: Context) -> dict[str, Any]:
    """Get version check status."""
    return await get_client().get_server_version_check(get_user_token())

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_server_version_history(ctx: Context) -> dict[str, Any]:
    """Get version history."""
    result = await get_client().get_server_version_history(get_user_token())
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_server_apk_links(ctx: Context) -> dict[str, Any]:
    """Get APK download links."""
    return     await get_client().get_server_apk_links(get_user_token())

# =============================================================================
# Asset Tools
# =============================================================================

@mcp.tool(tags={"read", "basic", "immich"})
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

@mcp.tool(tags={"read", "primary", "immich"})
async def get_asset_statistics(ctx: Context) -> dict[str, Any]:
    """Get asset statistics (total count, image/video counts)."""
    return await get_client().get_asset_statistics(get_user_token())

@mcp.tool(tags={"read", "primary", "immich"})
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

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_asset_ocr(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get OCR data for an asset.

    Args:
        id: The unique ID of the asset.
    """
    data = await get_client().get_asset_ocr(id, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_asset_metadata(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get metadata for an asset.

    Args:
        id: The unique ID of the asset.
    """
    data = await get_client().get_asset_metadata(id, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_asset_metadata_by_key(
    id: str,
    key: str,
    ctx: Context
) -> dict[str, Any]:
    """Get specific metadata key for an asset.

    Args:
        id: The unique ID of the asset.
        key: The metadata key.
    """
    return await get_client().get_asset_metadata_by_key(id, key, get_user_token())

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_asset_edits(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get edit history for an asset.

    Args:
        id: The unique ID of the asset.
    """
    return await get_client().get_asset_edits(id, get_user_token())

@mcp.tool(tags={"read", "basic", "immich"})
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

@mcp.tool(tags={"read", "basic", "immich"})
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

@mcp.tool(tags={"read", "basic", "immich"})
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

@mcp.tool(tags={"write", "primary", "immich"})
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
        isFavorite: Mark as favorite.
        description: Asset description.
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        dateTimeOriginal: ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        rating: Rating in range [1-5] (starred), -1 (rejected), or null (unrated).
        visibility: Asset visibility (PUBLIC, PRIVATE).
        livePhotoVideoId: Live photo video ID.
    """
    params = UpdateAssetParam(
        isFavorite=isFavorite, description=description,
        latitude=latitude, longitude=longitude,
        dateTimeOriginal=dateTimeOriginal, rating=rating,
        visibility=visibility, livePhotoVideoId=livePhotoVideoId,
    )
    return await get_client().update_asset(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "advanced", "immich"})
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
    return await get_client().update_asset_edits(id, payload, get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
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
    result = await get_client().update_asset_metadata(id, payload, get_user_token())
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(tags={"write", "primary", "immich"})
async def delete_assets(
ids: str,
ctx: Context,
force: bool = False,
) -> dict[str, Any]:
    """Delete assets by IDs.

    Args:
        ids: Comma-separated list of asset IDs to delete.
        force: Force delete even if in trash.
    """
    id_list = [x.strip() for x in ids.split(",") if x.strip()]
    payload = {"ids": id_list}
    if force:
        payload["force"] = True
    return await get_client().delete_assets(payload, get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
async def bulk_update_assets(
ids: str,
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
        ids: Comma-separated list of asset IDs to update.
        isFavorite: Mark as favorite.
        description: Asset description.
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        dateTimeOriginal: ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        rating: Rating in range [1-5], -1, or null.
        visibility: Asset visibility.
        duplicateId: Duplicate ID.
        timeZone: Time zone (IANA timezone).
    """
    id_list = [x.strip() for x in ids.split(",") if x.strip()]
    params = AssetBulkUpdateParam(
        ids=id_list,
        isFavorite=isFavorite, description=description,
        latitude=latitude, longitude=longitude,
        dateTimeOriginal=dateTimeOriginal, rating=rating,
        visibility=visibility, duplicateId=duplicateId, timeZone=timeZone,
    )
    return await get_client().bulk_update_assets(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "advanced", "immich"})
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
        sidecar: Copy sidecar file.
        stack: Copy stack association.
    """
    params = CopyAssetParam(
        sourceId=sourceId, targetId=targetId,
        albums=albums, favorite=favorite,
        sharedLinks=sharedLinks, sidecar=sidecar, stack=stack,
    )
    return await get_client().copy_asset(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"read", "basic", "immich"})
async def get_all_assets(
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
    personIds: str = "",
    tagIds: str = "",
    albumIds: str = "",
    libraryId: Optional[str] = None,
    order: Optional[str] = None,
    withExif: bool = False,
    withPeople: bool = False,
    withStacked: bool = False,
) -> dict[str, Any]:
    """List all assets with optional filters and pagination.

    Args:
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 100.
        include_all_fields: Default False (common fields only). Set True for all fields.
        type: Asset type (IMAGE, VIDEO, AUDIO, OTHER).
        isFavorite: Filter by favorite status.
        isMotion: Filter by motion photo.
        isOffline: Filter by offline status.
        isNotInAlbum: Filter assets not in any album.
        takenAfter: Filter by taken date after. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        takenBefore: Filter by taken date before. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        originalFileName: Filter by original file name.
        city: Filter by city name.
        state: Filter by state/province name.
        country: Filter by country name.
        make: Filter by camera make.
        model: Filter by camera model.
        personIds: Comma-separated person IDs.
        tagIds: Comma-separated tag IDs.
        albumIds: Comma-separated album IDs.
        libraryId: Library ID to filter by.
        order: Sort order (asc, desc).
        withExif: Include EXIF data.
        withPeople: Include people data.
        withStacked: Include stacked assets.
    """
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
    if personIds: payload["personIds"] = [p.strip() for p in personIds.split(",") if p.strip()]
    if tagIds: payload["tagIds"] = [t.strip() for t in tagIds.split(",") if t.strip()]
    if albumIds: payload["albumIds"] = [a.strip() for a in albumIds.split(",") if a.strip()]
    if libraryId: payload["libraryId"] = libraryId
    if order: payload["order"] = order
    if withExif: payload["withExif"] = True
    if withPeople: payload["withPeople"] = True
    if withStacked: payload["withStacked"] = True
    return await get_client().search_metadata(
        payload, get_user_token(), include_all_fields=include_all_fields
    )

@mcp.tool(tags={"read", "primary", "immich"})
async def get_assets_by_tag(
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
        include_all_fields=include_all_fields,
    )

@mcp.tool(tags={"read", "primary", "immich"})
async def get_album_assets(
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
        include_all_fields=include_all_fields,
    )

@mcp.tool(tags={"read", "primary", "immich"})
async def get_memory_assets(
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
        memoryId, get_user_token(), include_all_fields=include_all_fields,
    )
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"write", "basic", "immich"})
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
        fileCreatedAt: File creation timestamp ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        fileModifiedAt: File modification timestamp ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        filename: Original filename.
        duration: Duration in seconds (for video assets).
        isFavorite: Mark as favorite.
        visibility: Asset visibility (public, private).
    """
    return await get_client().upload_asset(
        base64_data, deviceAssetId, deviceId, fileCreatedAt, fileModifiedAt, get_user_token(),
        filename=filename, duration=duration,
        is_favorite=isFavorite, visibility=visibility,
    )

# =============================================================================
# Album Tools
# =============================================================================

@mcp.tool(tags={"read", "basic", "immich"})
async def get_all_albums(
ctx: Context,
include_all_fields: bool = False,
) -> dict[str, Any]:
    """List all albums.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
            every album in the response.
    """
    data = await get_client().get_all_albums(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
    )
    return {"items": json_to_toon(data)}

@mcp.tool(tags={"read", "basic", "immich"})
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

@mcp.tool(tags={"write", "basic", "immich"})
async def create_album(
albumName: str,
ctx: Context,
description: str = "",
albumUsers: str = "",
assetIds: str = "",
) -> dict[str, Any]:
    """Create a new album.

    Args:
        albumName: Name of the album.
        description: Description of the album.
        albumUsers: Comma-separated user IDs to share with.
        assetIds: Comma-separated asset IDs to add initially.
    """
    users_list = [{"userId": u.strip()} for u in albumUsers.split(",") if u.strip()] if albumUsers else []
    asset_list = [a.strip() for a in assetIds.split(",") if a.strip()] if assetIds else []
    params = CreateAlbumParam(albumName=albumName, description=description)
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    if users_list:
        payload["albumUsers"] = users_list
    if asset_list:
        payload["assetIds"] = asset_list
    return await get_client().create_album(payload, get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
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
        isActivityEnabled: Enable activity feed.
        order: Asset order (e.g. desc, asc).
    """
    params = UpdateAlbumParam(
        albumName=albumName, description=description,
        albumThumbnailAssetId=albumThumbnailAssetId,
        isActivityEnabled=isActivityEnabled, order=order,
    )
    return await get_client().update_album(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "primary", "immich"})
async def delete_album_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete an album by ID.

    Args:
        id: The unique ID of the album to delete.
    """
    return await get_client().delete_album_by_id(id, get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
async def add_assets_to_album(
    id: str,
    assetIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Add assets to an album.

    Args:
        id: The unique ID of the album.
        assetIds: Comma-separated asset IDs.
    """
    id_list = [a.strip() for a in assetIds.split(",") if a.strip()]
    payload = {"ids": id_list}
    data = await get_client().add_assets_to_album(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"write", "primary", "immich"})
async def remove_assets_from_album(
    id: str,
    assetIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Remove assets from an album.

    Args:
        id: The unique ID of the album.
        assetIds: Comma-separated asset IDs.
    """
    id_list = [a.strip() for a in assetIds.split(",") if a.strip()]
    payload = {"ids": id_list}
    data = await get_client().remove_assets_from_album(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"write", "primary", "immich"})
async def share_album_with_users(
    id: str,
    albumUsers: str,
    ctx: Context
) -> dict[str, Any]:
    """Share an album with other users.

    Args:
        id: The unique ID of the album.
        albumUsers: Comma-separated user IDs to share with.
    """
    users_list = [{"userId": u.strip()} for u in albumUsers.split(",") if u.strip()]
    payload = {"albumUsers": users_list}
    return await get_client().add_users_to_album(id, payload, get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
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

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_album_statistics(ctx: Context) -> dict[str, Any]:
    """Get album statistics."""
    return await get_client().get_album_statistics(get_user_token())

@mcp.tool(tags={"read", "primary", "immich"})
async def get_album_map_markers(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get map markers for an album.

    Args:
        id: The unique ID of the album.
    """
    data = await get_client().get_album_map_markers(id, get_user_token())
    return {"results": data} if isinstance(data, list) else data

# =============================================================================
# Tag Tools
# =============================================================================

@mcp.tool(tags={"read", "basic", "immich"})
async def get_all_tags(
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

@mcp.tool(tags={"read", "primary", "immich"})
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

@mcp.tool(tags={"write", "primary", "immich"})
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
    return await get_client().create_tag(payload, get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
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
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "primary", "immich"})
async def delete_tag_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a tag by ID.

    Args:
        id: The unique ID of the tag to delete.
    """
    return await get_client().delete_tag_by_id(id, get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
async def upsert_tags(
    tags: str,
    ctx: Context
) -> dict[str, Any]:
    """Upsert tags by name.

    Args:
        tags: Comma-separated tag names to upsert.
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    payload = {"tags": tag_list}
    data = await get_client().upsert_tags(payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"write", "primary", "immich"})
async def tag_assets(
    assetIds: str,
    tagIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Tag assets with specified tags.

    Args:
        assetIds: Comma-separated asset IDs.
        tagIds: Comma-separated tag IDs.
    """
    asset_list = [a.strip() for a in assetIds.split(",") if a.strip()]
    tag_list = [t.strip() for t in tagIds.split(",") if t.strip()]
    payload = {"assetIds": asset_list, "tagIds": tag_list}
    return await get_client().tag_assets(payload, get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
async def tag_assets_by_tag(
    id: str,
    assetIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Tag assets with a specific tag.

    Args:
        id: The tag ID.
        assetIds: Comma-separated asset IDs.
    """
    asset_list = [a.strip() for a in assetIds.split(",") if a.strip()]
    payload = {"ids": asset_list}
    data = await get_client().tag_assets_by_tag(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"write", "primary", "immich"})
async def untag_assets(
    id: str,
    assetIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Remove a tag from assets.

    Args:
        id: The tag ID.
        assetIds: Comma-separated asset IDs.
    """
    asset_list = [a.strip() for a in assetIds.split(",") if a.strip()]
    payload = {"ids": asset_list}
    data = await get_client().untag_assets(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

# =============================================================================
# People / Faces Tools
# =============================================================================

@mcp.tool(tags={"read", "basic", "immich"})
async def get_all_people(
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

@mcp.tool(tags={"read", "primary", "immich"})
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

@mcp.tool(tags={"write", "primary", "immich"})
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
        birthDate: Person date of birth. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        color: Person color in hex format.
        isFavorite: Mark as favorite.
        isHidden: Person visibility (hidden).
    """
    params = CreatePersonParam(
        name=name, birthDate=birthDate, color=color,
        isFavorite=isFavorite, isHidden=isHidden,
    )
    return await get_client().create_person(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "primary", "immich"})
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
        birthDate: Person date of birth. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        color: Person color in hex format.
        isFavorite: Mark as favorite.
        isHidden: Person visibility (hidden).
        featureFaceAssetId: Asset ID used for feature face thumbnail.
    """
    params = UpdatePersonParam(
        name=name, birthDate=birthDate, color=color,
        isFavorite=isFavorite, isHidden=isHidden,
        featureFaceAssetId=featureFaceAssetId,
    )
    return await get_client().update_person(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "primary", "immich"})
async def delete_person_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a person by ID.

    Args:
        id: The unique ID of the person to delete.
    """
    return await get_client().delete_person_by_id(id, get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
async def merge_people(
    id: str,
    mergeIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Merge people into a single person.

    Args:
        id: The target person ID to keep.
        mergeIds: Comma-separated person IDs to merge into the target.
    """
    id_list = [i.strip() for i in mergeIds.split(",") if i.strip()]
    payload = {"ids": id_list}
    data = await get_client().merge_people(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_person_statistics(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get statistics for a person.

    Args:
        id: The unique ID of the person.
    """
    return await get_client().get_person_statistics(id, get_user_token())

@mcp.tool(tags={"read", "primary", "immich"})
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

@mcp.tool(tags={"read", "primary", "immich"})
async def get_faces_by_asset(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get faces detected in an asset.

    Args:
        id: The unique ID of the asset.
    """
    data = await get_client().get_faces_by_asset(id, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"write", "advanced", "immich"})
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
    data = await get_client().reassign_faces(personId, payload, get_user_token())
    return {"results": data} if isinstance(data, list) else data

@mcp.tool(tags={"write", "advanced", "immich"})
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

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_all_libraries(
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

@mcp.tool(tags={"read", "advanced", "immich"})
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

@mcp.tool(tags={"write", "advanced", "immich"})
async def create_library(
ownerId: str,
ctx: Context,
name: str = "",
importPaths: str = "",
exclusionPatterns: str = "",
) -> dict[str, Any]:
    """Create a new library.

    Args:
        ownerId: Owner user ID.
        name: Library name.
        importPaths: Comma-separated import paths.
        exclusionPatterns: Comma-separated exclusion patterns.
    """
    import_list = [p.strip() for p in importPaths.split(",") if p.strip()] if importPaths else []
    exclude_list = [p.strip() for p in exclusionPatterns.split(",") if p.strip()] if exclusionPatterns else []
    params = CreateLibraryParam(ownerId=ownerId, name=name)
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    if import_list:
        payload["importPaths"] = import_list
    if exclude_list:
        payload["exclusionPatterns"] = exclude_list
    return await get_client().create_library(payload, get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
async def update_library(
id: str,
ctx: Context,
name: Optional[str] = None,
importPaths: Optional[str] = None,
exclusionPatterns: Optional[str] = None,
) -> dict[str, Any]:
    """Update a library.

    Args:
        id: The unique ID of the library.
        name: Library name.
        importPaths: Comma-separated import paths.
        exclusionPatterns: Comma-separated exclusion patterns.
    """
    params = UpdateLibraryParam(name=name)
    payload = params.model_dump(exclude_unset=True, exclude_none=True)
    if importPaths is not None:
        payload["importPaths"] = [p.strip() for p in importPaths.split(",") if p.strip()]
    if exclusionPatterns is not None:
        payload["exclusionPatterns"] = [p.strip() for p in exclusionPatterns.split(",") if p.strip()]
    return await get_client().update_library(id, payload, get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
async def delete_library_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a library by ID.

    Args:
        id: The unique ID of the library to delete.
    """
    return await get_client().delete_library_by_id(id, get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
async def scan_library(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Scan a library for new files.

    Args:
        id: The unique ID of the library.
    """
    return await get_client().scan_library(id, get_user_token())

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_library_statistics(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Get statistics for a library.

    Args:
        id: The unique ID of the library.
    """
    return await get_client().get_library_statistics(id, get_user_token())

# =============================================================================
# Memory Tools
# =============================================================================

@mcp.tool(tags={"read", "primary", "immich"})
async def get_all_memories(
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

@mcp.tool(tags={"read", "primary", "immich"})
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

@mcp.tool(tags={"write", "advanced", "immich"})
async def create_memory(
type: str,
memoryAt: str,
year: int,
ctx: Context,
assetIds: str = "",
isSaved: bool = False,
hideAt: str = "",
showAt: str = "",
seenAt: str = "",
) -> dict[str, Any]:
    """Create a new memory.

    Args:
        type: Memory type (on_this_day).
        memoryAt: Memory date. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        year: Year for the on_this_day memory.
        assetIds: Comma-separated asset IDs.
        isSaved: Save memory.
        hideAt: Date when memory should be hidden. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        showAt: Date when memory should be shown. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        seenAt: Date when memory was seen. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
    """
    asset_list = [a.strip() for a in assetIds.split(",") if a.strip()] if assetIds else []
    payload = {
        "type": type,
        "memoryAt": _normalize_datetime(memoryAt),
        "data": {"year": year},
    }
    if asset_list:
        payload["assetIds"] = asset_list
    if isSaved:
        payload["isSaved"] = True
    if hideAt:
        payload["hideAt"] = _normalize_datetime(hideAt)
    if showAt:
        payload["showAt"] = _normalize_datetime(showAt)
    if seenAt:
        payload["seenAt"] = _normalize_datetime(seenAt)
    return await get_client().create_memory(payload, get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
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
        isSaved: Save memory.
        memoryAt: Memory date. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        seenAt: Date when memory was seen. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
    """
    params = UpdateMemoryParam(isSaved=isSaved, memoryAt=memoryAt, seenAt=seenAt)
    return await get_client().update_memory(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "advanced", "immich"})
async def delete_memory_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a memory by ID.

    Args:
        id: The unique ID of the memory to delete.
    """
    return await get_client().delete_memory_by_id(id, get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
async def add_assets_to_memory(
    id: str,
    assetIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Add assets to a memory.

    Args:
        id: The unique ID of the memory.
        assetIds: Comma-separated asset IDs.
    """
    asset_list = [a.strip() for a in assetIds.split(",") if a.strip()]
    payload = {"ids": asset_list}
    data = await get_client().add_assets_to_memory(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"write", "advanced", "immich"})
async def remove_assets_from_memory(
    id: str,
    assetIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Remove assets from a memory.

    Args:
        id: The unique ID of the memory.
        assetIds: Comma-separated asset IDs to remove.
    """
    asset_list = [a.strip() for a in assetIds.split(",") if a.strip()]
    payload = {"ids": asset_list}
    data = await get_client().remove_assets_from_memory(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_memory_statistics(ctx: Context) -> dict[str, Any]:
    """Get memory statistics."""
    return await get_client().get_memory_statistics(get_user_token())

# =============================================================================
# Stack Tools
# =============================================================================

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_all_stacks(
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

@mcp.tool(tags={"read", "advanced", "immich"})
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

@mcp.tool(tags={"write", "advanced", "immich"})
async def create_stack(
    assetIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Create a stack from assets (minimum 2 assets).

    Args:
        assetIds: Comma-separated asset IDs. First becomes primary (required, min 2).
    """
    asset_list = [a.strip() for a in assetIds.split(",") if a.strip()]
    payload = {"assetIds": asset_list}
    return await get_client().create_stack(payload, get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
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
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "advanced", "immich"})
async def delete_stack_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a stack by ID.

    Args:
        id: The unique ID of the stack to delete.
    """
    return await get_client().delete_stack_by_id(id, get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
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

@mcp.tool(tags={"read", "primary", "immich"})
async def get_all_shared_links(
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

@mcp.tool(tags={"read", "primary", "immich"})
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

@mcp.tool(tags={"write", "primary", "immich"})
async def create_shared_link(
type: str,
ctx: Context,
assetIds: str = "",
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
        type: Type of shared link (ALBUM or INDIVIDUAL).
        assetIds: Comma-separated asset IDs (for INDIVIDUAL type).
        albumId: Album ID (for ALBUM type).
        description: Link description.
        expiresAt: Expiration date. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
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
        payload["assetIds"] = [a.strip() for a in assetIds.split(",") if a.strip()]
    if albumId:
        payload["albumId"] = albumId
    return await get_client().create_shared_link(payload, get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
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
        expiresAt: Expiration date. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
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
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "primary", "immich"})
async def delete_shared_link_by_id(
    id: str,
    ctx: Context
) -> dict[str, Any]:
    """Delete a shared link by ID.

    Args:
        id: The unique ID of the shared link to delete.
    """
    return await get_client().delete_shared_link_by_id(id, get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
async def add_assets_to_shared_link(
    id: str,
    assetIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Add assets to a shared link.

    Args:
        id: The unique ID of the shared link.
        assetIds: Comma-separated asset IDs to add.
    """
    asset_list = [a.strip() for a in assetIds.split(",") if a.strip()]
    payload = {"assetIds": asset_list}
    data = await get_client().add_assets_to_shared_link(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

@mcp.tool(tags={"write", "primary", "immich"})
async def remove_assets_from_shared_link(
    id: str,
    assetIds: str,
    ctx: Context
) -> dict[str, Any]:
    """Remove assets from a shared link.

    Args:
        id: The unique ID of the shared link.
        assetIds: Comma-separated asset IDs to remove.
    """
    asset_list = [a.strip() for a in assetIds.split(",") if a.strip()]
    payload = {"assetIds": asset_list}
    data = await get_client().remove_assets_from_shared_link(id, payload, get_user_token())
    return {"items": data} if isinstance(data, list) else data

# =============================================================================
# Activity Tools
# =============================================================================

@mcp.tool(tags={"read", "primary", "immich"})
async def get_all_activities(
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
        level: Filter by reaction level.
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

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_activity_statistics(
albumId: str,
ctx: Context,
assetId: str = "",
) -> dict[str, Any]:
    """Get activity statistics for an album.

    Args:
        albumId: Album ID.
        assetId: Asset ID.
    """
    params = {"albumId": albumId}
    if assetId:
        params["assetId"] = assetId
    return await get_client().get_activity_statistics(get_user_token(), params=params)

@mcp.tool(tags={"write", "primary", "immich"})
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
    return await get_client().create_activity(payload, get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
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

@mcp.tool(tags={"read", "primary", "immich"})
async def get_all_partners(
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

@mcp.tool(tags={"write", "advanced", "immich"})
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
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "advanced", "immich"})
async def update_partner(
    id: str,
    inTimeline: bool,
    ctx: Context
) -> dict[str, Any]:
    """Update a partner's timeline visibility.

    Args:
        id: Partner (user) ID.
        inTimeline: Show partner assets in timeline.
    """
    params = UpdatePartnerParam(inTimeline=inTimeline)
    return await get_client().update_partner(
        id, params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"write", "advanced", "immich"})
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

@mcp.tool(tags={"read", "basic", "immich"})
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
personIds: str = "",
tagIds: str = "",
albumIds: str = "",
libraryId: Optional[str] = None,
order: Optional[str] = None,
withExif: bool = False,
withPeople: bool = False,
withStacked: bool = False,
) -> dict[str, Any]:
    """Search assets by metadata fields.

    Args:
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 50.
        query: General search query.
        type: Asset type (IMAGE, VIDEO, AUDIO, OTHER).
        isFavorite: Filter by favorite status.
        isMotion: Filter by motion photo.
        isOffline: Filter by offline status.
        isNotInAlbum: Filter assets not in any album.
        takenAfter: Filter by taken date after. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        takenBefore: Filter by taken date before. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        originalFileName: Filter by original file name.
        city: Filter by city name.
        state: Filter by state/province name.
        country: Filter by country name.
        make: Filter by camera make.
        model: Filter by camera model.
        personIds: Comma-separated person IDs.
        tagIds: Comma-separated tag IDs.
        albumIds: Comma-separated album IDs.
        libraryId: Library ID to filter by.
        order: Sort order (asc, desc).
        withExif: Include EXIF data.
        withPeople: Include people data.
        withStacked: Include stacked assets.
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
    if personIds: payload["personIds"] = [p.strip() for p in personIds.split(",") if p.strip()]
    if tagIds: payload["tagIds"] = [t.strip() for t in tagIds.split(",") if t.strip()]
    if albumIds: payload["albumIds"] = [a.strip() for a in albumIds.split(",") if a.strip()]
    if libraryId: payload["libraryId"] = libraryId
    if order: payload["order"] = order
    if withExif: payload["withExif"] = True
    if withPeople: payload["withPeople"] = True
    if withStacked: payload["withStacked"] = True
    return await get_client().search_metadata(payload, get_user_token())

@mcp.tool(tags={"read", "basic", "immich"})
async def search_smart(
query: str,
ctx: Context,
page: int = 1,
size: int = 50,
type: Optional[str] = None,
isFavorite: Optional[bool] = None,
city: Optional[str] = None,
state: Optional[str] = None,
country: Optional[str] = None,
make: Optional[str] = None,
model: Optional[str] = None,
personIds: str = "",
tagIds: str = "",
albumIds: str = "",
libraryId: Optional[str] = None,
) -> dict[str, Any]:
    """Search assets using natural language (CLIP-based smart search).

    Args:
        query: Natural language search query.
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 50.
        type: Asset type.
        isFavorite: Filter by favorite.
        city: Filter by city.
        state: Filter by state.
        country: Filter by country.
        make: Filter by camera make.
        model: Filter by camera model.
        personIds: Comma-separated person IDs.
        tagIds: Comma-separated tag IDs.
        albumIds: Comma-separated album IDs.
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
    if personIds: payload["personIds"] = [p.strip() for p in personIds.split(",") if p.strip()]
    if tagIds: payload["tagIds"] = [t.strip() for t in tagIds.split(",") if t.strip()]
    if albumIds: payload["albumIds"] = [a.strip() for a in albumIds.split(",") if a.strip()]
    if libraryId: payload["libraryId"] = libraryId
    return await get_client().search_smart(payload, get_user_token())

@mcp.tool(tags={"read", "primary", "immich"})
async def search_suggestions(
    type: str,
    query: str,
    ctx: Context
) -> dict[str, Any]:
    """Get search suggestions.

    Args:
        type: Suggestion type (country, state, city, camera-make, camera-model, camera-lens-model).
        query: Search query text.
    """
    params = {"type": type, "query": query}
    result = await get_client().search_suggestions(params, get_user_token())
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(tags={"read", "primary", "immich"})
async def search_explore(ctx: Context) -> dict[str, Any]:
    """Get explore data grouped by city."""
    result = await get_client().search_explore(get_user_token())
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(tags={"read", "primary", "immich"})
async def search_cities(ctx: Context) -> dict[str, Any]:
    """Get assets grouped by city."""
    result = await get_client().search_cities(get_user_token())
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(tags={"read", "primary", "immich"})
async def search_random(
    ctx: Context,
    size: int = 100,
    type: Optional[str] = None,
    isFavorite: Optional[bool] = None,
    isMotion: Optional[bool] = None,
    isNotInAlbum: Optional[bool] = None,
    personIds: str = "",
    tagIds: str = "",
    albumIds: str = "",
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
        type: Asset type (IMAGE, VIDEO, AUDIO, OTHER).
        isFavorite: Filter by favorite status.
        isMotion: Filter by motion photo.
        isNotInAlbum: Filter assets not in any album.
        personIds: Comma-separated person IDs.
        tagIds: Comma-separated tag IDs.
        albumIds: Comma-separated album IDs.
        libraryId: Library ID.
        city: Filter by city name.
        state: Filter by state/province name.
        country: Filter by country name.
        make: Filter by camera make.
        model: Filter by camera model.
    """
    payload: dict[str, Any] = {"size": size}
    if type: payload["type"] = type
    if isFavorite is not None: payload["isFavorite"] = isFavorite
    if isMotion is not None: payload["isMotion"] = isMotion
    if isNotInAlbum is not None: payload["isNotInAlbum"] = isNotInAlbum
    if personIds: payload["personIds"] = [p.strip() for p in personIds.split(",") if p.strip()]
    if tagIds: payload["tagIds"] = [t.strip() for t in tagIds.split(",") if t.strip()]
    if albumIds: payload["albumIds"] = [a.strip() for a in albumIds.split(",") if a.strip()]
    if libraryId: payload["libraryId"] = libraryId
    if city: payload["city"] = city
    if state: payload["state"] = state
    if country: payload["country"] = country
    if make: payload["make"] = make
    if model: payload["model"] = model
    data = await get_client().search_random(payload, get_user_token())
    return {"results": data} if isinstance(data, list) else data

@mcp.tool(tags={"read", "primary", "immich"})
async def search_person(
    ctx: Context,
    name: str,
    withHidden: bool = False,
) -> dict[str, Any]:
    """Search for people by name.

    Args:
        name: Person name to search for.
        withHidden: Include hidden people.
    """
    params = {"name": name, "withHidden": withHidden}
    result = await get_client().search_person(params, get_user_token())
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(tags={"read", "advanced", "immich"})
async def search_places(
    ctx: Context,
    name: str,
) -> dict[str, Any]:
    """Search for places by name.

    Args:
        name: Place name to search for.
    """
    params = {"name": name}
    result = await get_client().search_places(params, get_user_token())
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(tags={"read", "primary", "immich"})
async def get_people_assets(
    ctx: Context,
    personIds: str,
    page: int = 1,
    size: int = 100,
    include_all_fields: bool = False,
    type: Optional[str] = None,
    isFavorite: Optional[bool] = None,
) -> dict[str, Any]:
    """List assets for specific people.

    Args:
        personIds: Comma-separated person IDs.
        page: Page number. Defaults to 1.
        size: Number of results per page. Defaults to 100.
        include_all_fields: Default False (common fields only). Set True for all fields.
        type: Asset type (IMAGE, VIDEO, AUDIO, OTHER).
        isFavorite: Filter by favorite status.
    """
    payload: dict[str, Any] = {"page": page, "size": size}
    pid_list = [p.strip() for p in personIds.split(",") if p.strip()]
    if pid_list:
        payload["personIds"] = pid_list
    if type: payload["type"] = type
    if isFavorite is not None: payload["isFavorite"] = isFavorite
    return await get_client().search_metadata(
        payload, get_user_token(), include_all_fields=include_all_fields,
    )

# =============================================================================
# Timeline & Map Tools
# =============================================================================

@mcp.tool(tags={"read", "basic", "immich"})
async def get_time_buckets(
size: str,
ctx: Context,
albumId: str = "",
personId: str = "",
userId: str = "",
) -> dict[str, Any]:
    """Get time buckets for timeline view.

    Args:
        size: Bucket size (MONTH, DAY).
        albumId: Filter by album.
        personId: Filter by person.
        userId: Filter by user.
    """
    params = {"size": size.upper() if size else "MONTH"}
    if albumId: params["albumId"] = albumId
    if personId: params["personId"] = personId
    if userId: params["userId"] = userId
    result = await get_client().get_time_buckets(params, get_user_token())
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(tags={"read", "basic", "immich"})
async def get_time_bucket(
size: str,
timeBucket: str,
ctx: Context,
albumId: str = "",
personId: str = "",
userId: str = "",
) -> dict[str, Any]:
    """Get assets in a specific time bucket.

    Args:
        size: Bucket size (MONTH, DAY).
        timeBucket: The time bucket key from get_time_buckets.
        albumId: Filter by album.
        personId: Filter by person.
        userId: Filter by user.
    """
    params = {"size": size.upper() if size else "MONTH", "timeBucket": timeBucket}
    if albumId: params["albumId"] = albumId
    if personId: params["personId"] = personId
    if userId: params["userId"] = userId
    data = await get_client().get_time_bucket(params, get_user_token())
    return {"items": json_to_toon(data)}

@mcp.tool(tags={"read", "primary", "immich"})
async def get_map_markers(
ctx: Context,
fileCreatedAfter: str = "",
fileCreatedBefore: str = "",
albumId: str = "",
personId: str = "",
withPartners: bool = False,
) -> dict[str, Any]:
    """Get map markers for assets with geolocation data.

    Args:
        fileCreatedAfter: Filter by file creation date after. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        fileCreatedBefore: Filter by file creation date before. ISO 8601 format (2026-06-22T15:00:00-04:00). (2026-06-22T15:00:00-04:00).
        albumId: Filter by album ID.
        personId: Filter by person ID.
        withPartners: Include partner assets.
    """
    params = {}
    if fileCreatedAfter: params["fileCreatedAfter"] = fileCreatedAfter
    if fileCreatedBefore: params["fileCreatedBefore"] = fileCreatedBefore
    if albumId: params["albumId"] = albumId
    if personId: params["personId"] = personId
    if withPartners: params["withPartners"] = "true"
    result = await get_client().get_map_markers(params, get_user_token())
    return {"results": result} if isinstance(result, list) else result

@mcp.tool(tags={"read", "advanced", "immich"})
async def reverse_geocode(
    lat: float,
    lon: float,
    ctx: Context
) -> dict[str, Any]:
    """Reverse geocode coordinates to a location.

    Args:
        lat: Latitude.
        lon: Longitude.
    """
    params = {"lat": lat, "lon": lon}
    result = await get_client().reverse_geocode(params, get_user_token())
    return {"results": result} if isinstance(result, list) else result

# =============================================================================
# Duplicate Tools
# =============================================================================

@mcp.tool(tags={"read", "primary", "immich"})
async def get_all_duplicates(
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

@mcp.tool(tags={"write", "primary", "immich"})
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

@mcp.tool(tags={"write", "primary", "immich"})
async def empty_trash(ctx: Context) -> dict[str, Any]:
    """Permanently empty the trash."""
    return await get_client().empty_trash(get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
async def restore_trash(ctx: Context) -> dict[str, Any]:
    """Restore all trashed assets."""
    return await get_client().restore_trash(get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
async def restore_trash_assets(
    ids: str,
    ctx: Context
) -> dict[str, Any]:
    """Restore specific trashed assets.

    Args:
        ids: Comma-separated asset IDs to restore.
    """
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    payload = {"ids": id_list}
    return await get_client().restore_trash_assets(payload, get_user_token())

# =============================================================================
# System Config Tools
# =============================================================================

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_system_config(ctx: Context) -> dict[str, Any]:
    """Get the full system configuration."""
    return await get_client().get_system_config(get_user_token())

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_system_config_defaults(ctx: Context) -> dict[str, Any]:
    """Get system configuration defaults."""
    return await get_client().get_system_config_defaults(get_user_token())

@mcp.tool(tags={"read", "advanced", "immich"})
async def get_storage_template_options(ctx: Context) -> dict[str, Any]:
    """Get available storage template options."""
    return await get_client().get_storage_template_options(get_user_token())

# =============================================================================
# User & Account Tools
# =============================================================================

@mcp.tool(tags={"read", "primary", "immich"})
async def get_all_users(
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

@mcp.tool(tags={"read", "primary", "immich"})
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

@mcp.tool(tags={"read", "basic", "immich"})
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

@mcp.tool(tags={"write", "primary", "immich"})
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
        avatarColor: Preferred avatar color.
    """
    params = UpdateMyUserParam(
        email=email, name=name, password=password, avatarColor=avatarColor,
    )
    return await get_client().update_my_user(
        params.model_dump(exclude_unset=True, exclude_none=True), get_user_token()
    )

@mcp.tool(tags={"read", "primary", "immich"})
async def get_my_preferences(ctx: Context) -> dict[str, Any]:
    """Get the current user's preferences."""
    return await get_client().get_my_preferences(get_user_token())

@mcp.tool(tags={"write", "primary", "immich"})
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
        albums_defaultAssetOrder: Default sort order for album assets. 'asc' or 'desc'.
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

@mcp.tool(tags={"read", "primary", "immich"})
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

@mcp.tool(tags={"write", "primary", "immich"})
async def delete_my_onboarding(ctx: Context) -> dict[str, Any]:
    """Delete the current user's onboarding status."""
    return await get_client().delete_my_onboarding(get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
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
    return await get_client().create_user(payload, get_user_token())

@mcp.tool(tags={"write", "advanced", "immich"})
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
    app = mcp.http_app(path=path)
    app = AuthMiddleware(app)
    print(f"Starting Immich MCP server on http://{host}:{port}{path}")
    import uvicorn
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
