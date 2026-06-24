# Immich MCP Server

This repository contains a Model Context Protocol (MCP) server that acts
as a secure, multi-tenant proxy between an AI Assistant and the Immich
backend API. It exposes **114 MCP tools** covering 16 resource domains
with full CRUD, search, timeline, map, and relationship management.

## ✨ Features

- **🔑 Identity Passthrough** — Extracts the `Authorization: Bearer <token>`
  header from incoming HTTP requests and forwards it to the Immich API
  without server-side authentication.
- **👥 Multi-Tenancy** — Uses Python `contextvars` to maintain thread-safe
  user identity isolation, ensuring all AI-driven actions are scoped to
  the authenticated user's permissions.
- **📊 Full Immich Coverage** — 114 tools mapped to Immich API endpoints
  across 16 resource domains.
- **⚡ TOON Optimization** — Bulk list responses are automatically compressed
  using TOON (Token-Optimized Object Notation) to reduce token consumption
  and maximize context window efficiency.
- **⚡ Efficient Gets** — GET responses return only commonly used fields by
  default. Full objects are available via an `include_all_fields` flag.
- **🧪 Comprehensive Testing** — 133 automated tests covering all tool
  domains, run via the test runner pipeline.

## 🔧 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `IMMICH_BASE_URL` | Yes | Docker-internal URL of the Immich server (e.g. `http://immich-app:2283`). |
| `MCP_SERVER_PORT` | Yes | Port number the MCP server listens on |
| `ALLOW_ALL_AGGREGATE` | No | When `true`, aggregate listing tools honor the `include_all_fields` parameter. When `false` (default), the parameter is silently forced to `False` for aggregate list operations. |
| `IMMICH_PUBLIC_URL` | No | Public-facing base URL of the Immich server (e.g. `https://immich.example.com`). Used to construct user-accessible URLs for thumbnails, originals, and profile images. Defaults to `IMMICH_BASE_URL` if not set. |

## 📦 Installation & Local Development

1. Ensure you have Python 3.12+ installed.
2. Install dependencies:
    ```bash
    pip install fastmcp httpx pydantic uvicorn toon-mcp-server
    ```
3. Run the server:
    ```bash
    export IMMICH_BASE_URL=http://localhost:2283
    export MCP_SERVER_PORT=80
    python -m src.main
    ```

## 🐳 Docker Deployment

Build and run the server using Docker:

```bash
docker build -t immich-mcp:latest .
docker run -d --name immich-mcp \
    -e IMMICH_BASE_URL="http://immich-app:2283" \
    -e IMMICH_PUBLIC_URL="https://immich.example.com" \
    -e MCP_SERVER_PORT=80 \
    immich-mcp:latest

The MCP server serves at `http://immich-mcp:80/mcp` (Streamable HTTP).
```

## ⚠️ Important Notes

- **📋 `include_all_fields`** — The `include_all_fields` parameter (available
  on all `get_*` and `list_*` tools) controls whether all available fields
  are included in responses. Defaults to `False` for performance; set to
  `True` only when additional fields are needed.
- **🔒 `ALLOW_ALL_AGGREGATE`** — Controls whether aggregate listing tools respect the `include_all_fields` parameter. When set to `false` (default), all aggregate list operations silently return only default fields regardless of the caller's request.
- **⚡ TOON Compression** — All bulk list responses are automatically
  compressed using TOON to reduce token consumption by 30–60%.
- **📝 Required Fields & Defaults** — Each `create_*` tool requires specific
  key fields. All other fields default to empty strings or reasonable values.
  The owner/user assignment field is automatically set to the authenticated
  user for most resources.

## 🛠️ API Tool Mapping

The server implements 114 MCP tools organized into the following categories:

### 🖼️ Asset Management (14 tools)

- `get_asset_by_id` — Get a single asset by ID
- `get_asset_statistics` — Get asset statistics
- `get_asset_ocr` — Get OCR data for an asset
- `get_asset_metadata` — Get metadata for an asset
- `get_asset_metadata_by_key` — Get a specific metadata key
- `get_asset_edits` — Get edit history
- `get_asset_thumbnail_url` — Get thumbnail URL
- `get_asset_original_url` — Get original file URL
- `update_asset` — Update an asset
- `update_asset_edits` — Apply edits to an asset
- `update_asset_metadata` — Update asset metadata
- `delete_assets` — Delete assets
- `bulk_update_assets` — Update multiple assets
- `copy_asset` — Copy asset metadata

### 💿 Album Management (11 tools)

- `get_all_albums` — List all albums
- `get_album_by_id` — Get a single album
- `create_album` — Create a new album
- `update_album` — Update an album
- `delete_album_by_id` — Delete an album
- `add_assets_to_album` — Add assets to an album
- `remove_assets_from_album` — Remove assets from an album
- `share_album_with_users` — Share album with users
- `remove_user_from_album` — Remove user from album
- `get_album_statistics` — Get album statistics
- `get_album_map_markers` — Get album map markers

### 🏷️ Tag Management (9 tools)

- `get_all_tags` — List all tags
- `get_tag_by_id` — Get a single tag
- `create_tag` — Create a tag
- `update_tag` — Update a tag
- `delete_tag_by_id` — Delete a tag
- `upsert_tags` — Upsert tags by name
- `tag_assets` — Tag assets
- `tag_assets_by_tag` — Tag assets with a specific tag
- `untag_assets` — Remove tag from assets

### 👤 People & Faces (11 tools)

- `get_all_people` — List all people
- `get_person_by_id` — Get a single person
- `create_person` — Create a person
- `update_person` — Update a person
- `delete_person_by_id` — Delete a person
- `merge_people` — Merge people
- `get_person_statistics` — Get person statistics
- `get_person_thumbnail_url` — Get person thumbnail URL
- `get_faces_by_asset` — Get faces for an asset
- `reassign_face` — Reassign a face to a different person
- `delete_face` — Delete a face

### 📚 Library Management (7 tools)

- `get_all_libraries` — List all libraries
- `get_library_by_id` — Get a single library
- `create_library` — Create a library
- `update_library` — Update a library
- `delete_library_by_id` — Delete a library
- `scan_library` — Scan a library
- `get_library_statistics` — Get library statistics

### 💭 Memory Management (7 tools)

- `get_all_memories` — List all memories
- `get_memory_by_id` — Get a single memory
- `create_memory` — Create a memory
- `update_memory` — Update a memory
- `delete_memory_by_id` — Delete a memory
- `add_assets_to_memory` — Add assets to a memory
- `get_memory_statistics` — Get memory statistics

### 🗃️ Stack Management (6 tools)

- `get_all_stacks` — List all stacks
- `get_stack_by_id` — Get a single stack
- `create_stack` — Create a stack
- `update_stack` — Update a stack
- `delete_stack_by_id` — Delete a stack
- `remove_asset_from_stack` — Remove asset from stack

### 🔗 Shared Link Management (5 tools)

- `get_all_shared_links` — List all shared links
- `get_shared_link_by_id` — Get a shared link
- `create_shared_link` — Create a shared link
- `update_shared_link` — Update a shared link
- `delete_shared_link_by_id` — Delete a shared link

### 📋 Activity Management (4 tools)

- `get_all_activities` — List activities
- `get_activity_statistics` — Get activity statistics
- `create_activity` — Create an activity
- `delete_activity_by_id` — Delete an activity

### 🤝 Partner Management (4 tools)

- `get_all_partners` — List partners
- `create_partner` — Add a partner
- `update_partner` — Update partner visibility
- `delete_partner_by_id` — Remove a partner

### 🖥️  Server (11 tools)

- `get_server_ping` — Ping the server
- `get_server_version` — Get server version
- `get_server_about` — Get server info
- `get_server_config` — Get server configuration
- `get_server_features` — Get feature flags
- `get_server_statistics` — Get server statistics
- `get_server_storage` — Get storage information
- `get_server_media_types` — Get supported media types
- `get_server_version_check` — Get version check status
- `get_server_version_history` — Get version history
- `get_server_apk_links` — Get APK download links

### 🔍 Search (5 tools)

- `search_metadata` — Search assets by metadata
- `search_smart` — Smart (CLIP) search
- `search_suggestions` — Get search suggestions
- `search_explore` — Explore data by city
- `search_cities` — Assets grouped by city

### 🗺️  Timeline & Map (4 tools)

- `get_time_buckets` — Get timeline buckets
- `get_time_bucket` — Get assets in a bucket
- `get_map_markers` — Get geolocation markers
- `reverse_geocode` — Reverse geocode coordinates

### 🔄 Duplicates & Trash (5 tools)

- `get_all_duplicates` — List duplicate groups
- `dismiss_duplicate_group` — Dismiss a duplicate group
- `empty_trash` — Empty trash
- `restore_trash` — Restore all trashed assets
- `restore_trash_assets` — Restore specific trashed assets

### ⚙️  System Config (3 tools)

- `get_system_config` — Get system configuration
- `get_system_config_defaults` — Get configuration defaults
- `get_storage_template_options` — Get storage template options

### 👥 User & Account (8 tools)

- `get_all_users` — List all users
- `get_user_by_id` — Get a user by ID
- `get_my_user_info` — Get current user info
- `update_my_user` — Update current user
- `get_my_preferences` — Get user preferences
- `update_my_preferences` — Update preferences
- `get_user_profile_image_url` — Get profile image URL
- `delete_my_onboarding` — Reset onboarding
