import os
import re
import json
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gsheet-mcp-server")


def parse_sheet_url(sheet_url: str) -> tuple[str, str]:
    sheet_url = sheet_url.strip()
    m = re.search(r'/d/([a-zA-Z0-9_-]+)', sheet_url)
    if not m:
        raise ValueError("invalid_sheet_url")
    spreadsheet_id = m.group(1)
    gid_match = re.search(r'[?&]gid=(\d+)', sheet_url)
    if not gid_match:
        gid_match = re.search(r'#gid=(\d+)', sheet_url)
    gid = gid_match.group(1) if gid_match else "0"
    return spreadsheet_id, gid


async def fetch_sheet_data(spreadsheet_id: str, gid: str) -> dict:
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/gviz/tq?tqx=out:json&gid={gid}&headers=1"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        text = resp.text

    stripped = text.strip()

    if stripped.startswith("<!") or stripped.startswith("<html"):
        raise ValueError("sheet_not_public")

    m = re.search(
        r'google\.visualization\.Query\.setResponse\((.+)\);?\s*$',
        stripped,
        re.DOTALL,
    )
    if not m:
        raise ValueError("sheet_not_public")

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        raise ValueError("sheet_not_public")

    if data.get("status") == "error":
        raise ValueError("sheet_not_public")

    return data


def build_columns_and_items(data: dict) -> tuple[list[str], list[dict]]:
    cols = data.get("table", {}).get("cols", [])
    rows = data.get("table", {}).get("rows", [])
    columns = [col.get("label", "") for col in cols]
    items = []
    for row in rows:
        cells = row.get("c", [])
        item = {}
        for i, col_name in enumerate(columns):
            if i < len(cells) and cells[i] is not None:
                cell = cells[i]
                if "v" in cell:
                    item[col_name] = cell["v"]
                elif "f" in cell:
                    item[col_name] = cell["f"]
                else:
                    item[col_name] = None
            else:
                item[col_name] = None
        items.append(item)
    return columns, items


@mcp.tool(
    description="Fetch data from a public Google Sheet in real time. Supports filtering by column with case-insensitive substring matching. IMPORTANT: Supply sheet_url directly as a plain string — do NOT wrap it inside a JSON 'query' string, and do NOT concatenate multiple JSON objects. Only ONE sheet_url per request."
)
async def get_sheet_data(
    sheet_url: str | None = None,
    filter_column: str | None = None,
    filter_value: str | None = None,
    query: str | None = None,
) -> dict:
    """Fetch data from a public Google Sheet.

    Args:
        sheet_url: Full Google Sheet URL as a plain string (e.g. .../d/{id}/edit?gid=0). Do NOT wrap in JSON or combine with other URLs.
        filter_column: Column name to filter on (requires filter_value)
        filter_value: Filter value (in, case-insensitive matching)
    """
    if query is not None:
        try:
            parsed = json.loads(query)
            if isinstance(parsed, dict):
                sheet_url = parsed.get("sheet_url", sheet_url)
                filter_column = parsed.get("filter_column", filter_column)
                filter_value = parsed.get("filter_value", filter_value)
        except json.JSONDecodeError:
            pass
        if not sheet_url and "}{" in query:
            return {"error": "batch_requests_not_supported", "detail": "Send one sheet_url per request"}

    if not sheet_url:
        return {"error": "invalid_sheet_url"}

    try:
        spreadsheet_id, gid = parse_sheet_url(sheet_url)
    except ValueError:
        return {"error": "invalid_sheet_url"}

    try:
        data = await fetch_sheet_data(spreadsheet_id, gid)
    except ValueError as e:
        return {"error": str(e)}
    except httpx.TimeoutException:
        return {"error": "fetch_failed", "detail": "Request timed out"}
    except Exception as e:
        return {"error": "fetch_failed", "detail": str(e)}

    columns, items = build_columns_and_items(data)

    if not columns:
        return {
            "sheet_id": spreadsheet_id,
            "tab_gid": gid,
            "total_matched": 0,
            "filtered": False,
            "columns": [],
            "items": [],
        }

    filtered = False
    warning = None

    if filter_column is not None and filter_value is not None:
        if filter_column not in columns:
            warning = "filter_column_not_found"
        else:
            fv = filter_value.strip().lower()
            items = [
                it
                for it in items
                if fv in (str(it.get(filter_column, "") or "").strip().lower())
            ]
            filtered = True

    result: dict = {
        "sheet_id": spreadsheet_id,
        "tab_gid": gid,
        "total_matched": len(items),
        "filtered": filtered,
        "columns": columns,
        "items": items,
    }
    if warning:
        result["warning"] = warning
    return result


def main():
    import sys

    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    if transport == "sse":
        import uvicorn

        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8000"))
        print(f"Starting MCP server on {host}:{port}", file=sys.stderr, flush=True)
        app = mcp.sse_app()
        uvicorn.run(app, host=host, port=port, log_level="info")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
