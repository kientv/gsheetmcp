# gsheetmcp — Public Google Sheet MCP server

Generic MCP server for reading public Google Sheet data via the **gviz** endpoint — no API key, OAuth, or service account required.

## Running

Default mode is **stdio** (for Claude Desktop / MCP Hub via `uvx`):

```bash
uvx gsheetmcp
```

Or run locally (from source):

```bash
cd sheet-mcp-server
uv run server.py
```

### SSE mode

Set env `MCP_TRANSPORT=sse` for HTTP SSE transport:

```bash
MCP_TRANSPORT=sse uv run server.py
```

Server exposes SSE endpoint `/sse` + `/messages` on `0.0.0.0:8000`. Configurable via:

| Env | Default | Description |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` or `sse` |
| `MCP_HOST` | `0.0.0.0` | Host (SSE mode) |
| `MCP_PORT` | `8000` | Port (SSE mode) |

## Tool: `get_sheet_data`

### Input

| Param | Type | Required | Description |
|---|---|---|---|
| `sheet_url` | `string` | yes | Full Google Sheet URL (with or without `gid`) |
| `filter_column` | `string` | no | Column name to filter on (requires `filter_value`) |
| `filter_value` | `string` | no | Filter value (`in` matching, case-insensitive) |

### Output

```json
{
  "sheet_id": "1p67eA4NGs389n-fuqHOmULhE5sfgRtFAulCHR8xcfGE",
  "tab_gid": "1253624571",
  "total_matched": 15,
  "filtered": true,
  "columns": ["Mã căn", "Tầng", "Diện tích", "Giá"],
  "items": [
    { "Mã căn": "A-1201", "Tầng": "12", "Diện tích": "85", "Giá": "2.5 tỷ" }
  ]
}
```

### Error responses

| Case | Response |
|---|---|
| Invalid URL format | `{"error": "invalid_sheet_url"}` |
| Sheet not public | `{"error": "sheet_not_public"}` |
| `filter_column` not found | Returns full data + `"warning": "filter_column_not_found"` |
| Empty tab | `{"items": [], "total_matched": 0}` |
| Timeout / network error | `{"error": "fetch_failed", "detail": "..."}` |

## Examples

### Sheet 1: FAQ (2 columns: Title, Description)

**URL:** `https://docs.google.com/spreadsheets/d/1zwblTR5DWzgOiVxsDYJJkP5Gcmi4OGiCtldI0nyxZGo/edit?gid=0`

**Request:**
```json
{
  "sheet_url": "https://docs.google.com/spreadsheets/d/1zwblTR5DWzgOiVxsDYJJkP5Gcmi4OGiCtldI0nyxZGo/edit?gid=0",
  "filter_column": "Title",
  "filter_value": "UI"
}
```

**Response:**
```json
{
  "sheet_id": "1zwblTR5DWzgOiVxsDYJJkP5Gcmi4OGiCtldI0nyxZGo",
  "tab_gid": "0",
  "total_matched": 3,
  "filtered": true,
  "columns": ["Title", "Description"],
  "items": [
    {
      "Title": "What's the difference between UI Kits and libraries",
      "Description": "UI Kits are copy-and-pastable components..."
    }
  ]
}
```

### Sheet 2: Inventory (completely different structure)

With a different sheet structure, `columns` and `items` adapt automatically — no column names leak between sheets.

### Test cases

1. Public sheet + valid filter → `filtered: true`, correct subset
2. Public sheet, no filter → `filtered: false`, all rows
3. Bad `filter_column` → full data + `warning: filter_column_not_found`
4. Private sheet → `error: sheet_not_public`
5. Invalid URL → `error: invalid_sheet_url`
6. Two sheets with different structures → columns/items adapt independently

## MCP client config

### stdio (recommended — default)

```json
{
  "mcpServers": {
    "gsheetmcp": {
      "command": "uvx",
      "args": ["git+https://github.com/kientv/gsheetmcp.git"]
    }
  }
}
```

Or with a local clone:

```json
{
  "mcpServers": {
    "gsheetmcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/gsheetmcp", "server.py"]
    }
  }
}
```

### SSE (remote server)

When the server runs in SSE mode, configure the client with the endpoint URL:

```json
{
  "mcpServers": {
    "gsheetmcp": {
      "transport": "sse",
      "url": "http://host:8000/sse"
    }
  }
}
```

## Limitations

- gviz is an internal Google Sheets endpoint, **not an official REST API** — no SLA.
- Works only with **public** sheets (Anyone with the link can view).
- Each call reads **1 tab** specified by `gid`.
- No write, delete, or data modification support.
- Large sheets may timeout (default 30s).
