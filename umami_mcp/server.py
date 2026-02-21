#!/usr/bin/env python3
"""Umami Analytics MCP Server — supports both Umami Cloud (API key) and self-hosted (user/pass)."""

import json
import os
import sys
import time
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import urllib.error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UMAMI_URL = os.environ.get("UMAMI_URL", "").rstrip("/")
UMAMI_API_KEY = os.environ.get("UMAMI_API_KEY", "")
UMAMI_USERNAME = os.environ.get("UMAMI_USERNAME", "")
UMAMI_PASSWORD = os.environ.get("UMAMI_PASSWORD", "")
UMAMI_USER_AGENT = os.environ.get("UMAMI_USER_AGENT", "umami-mcp/1.0")
UMAMI_CF_ACCESS_CLIENT_ID = os.environ.get("UMAMI_CF_ACCESS_CLIENT_ID", "")
UMAMI_CF_ACCESS_CLIENT_SECRET = os.environ.get("UMAMI_CF_ACCESS_CLIENT_SECRET", "")
UMAMI_DEBUG = os.environ.get("UMAMI_DEBUG", "").lower() in {"1", "true", "yes", "on"}

# Cloud uses /v1 path prefix; self-hosted uses /api
_is_cloud = bool(UMAMI_API_KEY)

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_self_hosted_token: str | None = None


def _base_url() -> str:
    """Return normalized API base URL for the current mode."""
    base = UMAMI_URL.rstrip("/")
    if _is_cloud:
        if not base:
            base = "https://api.umami.is"
        if base.endswith("/v1"):
            base = base[:-3]
        return base
    if base.endswith("/api"):
        base = base[:-4]
    return base


def _get_auth_headers() -> dict[str, str]:
    """Return auth headers depending on configuration mode."""
    if _is_cloud:
        return {"x-umami-api-key": UMAMI_API_KEY}

    global _self_hosted_token
    if _self_hosted_token is None:
        _self_hosted_token = _login_self_hosted()
    return {"Authorization": f"Bearer {_self_hosted_token}"}


def _get_request_headers() -> dict[str, str]:
    """Return common headers for all outbound requests."""
    headers = {
        "Accept": "application/json",
        "User-Agent": UMAMI_USER_AGENT,
    }
    if UMAMI_CF_ACCESS_CLIENT_ID and UMAMI_CF_ACCESS_CLIENT_SECRET:
        headers["CF-Access-Client-Id"] = UMAMI_CF_ACCESS_CLIENT_ID
        headers["CF-Access-Client-Secret"] = UMAMI_CF_ACCESS_CLIENT_SECRET
    return headers


def _login_self_hosted() -> str:
    """Authenticate against a self-hosted Umami instance and return a JWT."""
    url = f"{_base_url()}/api/auth/login"
    body = json.dumps({"username": UMAMI_USERNAME, "password": UMAMI_PASSWORD}).encode()
    headers = {
        **_get_request_headers(),
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["token"]


# ---------------------------------------------------------------------------
# Umami API helpers
# ---------------------------------------------------------------------------


def _api_url(path: str) -> str:
    """Build the full API URL. Cloud uses /v1 prefix, self-hosted uses /api."""
    base = _base_url()
    if _is_cloud:
        return f"{base}/v1{path}"
    return f"{base}/api{path}"


def _api_get(path: str, params: dict | None = None) -> object:
    """Make an authenticated GET request to the Umami API."""
    url = _api_url(path)
    if params:
        # Strip None values so optional params aren't sent
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    if UMAMI_DEBUG:
        print(f"[umami-mcp] GET {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={**_get_request_headers(), **_get_auth_headers()})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # Self-hosted JWT can expire during long-lived MCP sessions.
        if e.code == 401 and not _is_cloud:
            global _self_hosted_token
            _self_hosted_token = None
            retry_req = urllib.request.Request(url, headers={**_get_request_headers(), **_get_auth_headers()})
            with urllib.request.urlopen(retry_req) as resp:
                return json.loads(resp.read())
        raise


# ---------------------------------------------------------------------------
# Filter params common to stats/pageviews/metrics
# ---------------------------------------------------------------------------

FILTER_PARAMS = [
    {"name": "path", "description": "Filter by URL path", "required": False},
    {"name": "referrer", "description": "Filter by referrer", "required": False},
    {"name": "title", "description": "Filter by page title", "required": False},
    {"name": "query", "description": "Filter by query string", "required": False},
    {"name": "browser", "description": "Filter by browser name", "required": False},
    {"name": "os", "description": "Filter by operating system", "required": False},
    {
        "name": "device",
        "description": "Filter by device type (desktop, mobile, tablet)",
        "required": False,
    },
    {
        "name": "country",
        "description": "Filter by country code (e.g. US, DE)",
        "required": False,
    },
    {"name": "region", "description": "Filter by region", "required": False},
    {"name": "city", "description": "Filter by city", "required": False},
    {"name": "hostname", "description": "Filter by hostname", "required": False},
    {"name": "language", "description": "Filter by language", "required": False},
    {"name": "event", "description": "Filter by event name", "required": False},
    {"name": "tag", "description": "Filter by tag", "required": False},
]

RANGE_DESCRIPTION = (
    "Convenience range in UTC: last_24h, last_7d, last_30d, this_month, last_month. "
    "Use this instead of startAt/endAt to avoid timestamp mistakes."
)


def _pick_filters(args: dict) -> dict:
    """Extract filter params from tool arguments, dropping None values."""
    return {
        p["name"]: args[p["name"]]
        for p in FILTER_PARAMS
        if args.get(p["name"]) is not None
    }


def _ms_ts(value: object, field_name: str) -> int:
    """Parse Unix milliseconds from MCP args, accepting int or numeric strings."""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError(f"Invalid {field_name}: expected Unix milliseconds as integer")


def _month_start_ms(ref_ms: int) -> int:
    dt = datetime.fromtimestamp(ref_ms / 1000, tz=timezone.utc)
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


def _shift_month_start_ms(month_start_ms: int, months_delta: int) -> int:
    dt = datetime.fromtimestamp(month_start_ms / 1000, tz=timezone.utc)
    year = dt.year
    month = dt.month + months_delta
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    shifted = datetime(year, month, 1, tzinfo=timezone.utc)
    return int(shifted.timestamp() * 1000)


def _resolve_time_range(args: dict) -> tuple[int, int]:
    has_start = args.get("startAt") is not None
    has_end = args.get("endAt") is not None
    if has_start or has_end:
        if not (has_start and has_end):
            raise ValueError("Provide both startAt and endAt, or use range.")
        return _ms_ts(args["startAt"], "startAt"), _ms_ts(args["endAt"], "endAt")

    range_name = args.get("range")
    if not range_name:
        raise ValueError(
            "Missing time range. Provide startAt/endAt (Unix ms) or range "
            "(last_24h, last_7d, last_30d, this_month, last_month)."
        )

    now = int(time.time() * 1000)
    if range_name == "last_24h":
        return now - 24 * 60 * 60 * 1000, now
    if range_name == "last_7d":
        return now - 7 * 24 * 60 * 60 * 1000, now
    if range_name == "last_30d":
        return now - 30 * 24 * 60 * 60 * 1000, now
    if range_name == "this_month":
        return _month_start_ms(now), now
    if range_name == "last_month":
        this_month_start = _month_start_ms(now)
        last_month_start = _shift_month_start_ms(this_month_start, -1)
        return last_month_start, this_month_start - 1

    raise ValueError(f"Invalid range: {range_name}")


# ---------------------------------------------------------------------------
# Tool definitions (MCP schema)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_websites",
        "description": "List all tracked websites in your Umami account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Optional search text to filter websites by name or domain",
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination (default: 1)",
                },
                "pageSize": {
                    "type": "integer",
                    "description": "Number of results per page",
                },
                "includeTeams": {
                    "type": "boolean",
                    "description": "Include team-owned websites",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_stats",
        "description": (
            "Get summary statistics (pageviews, visitors, visits, bounces, totaltime) "
            "for a website over a date range. Timestamps are Unix milliseconds."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "websiteId": {"type": "string", "description": "Website UUID"},
                "startAt": {
                    "type": "integer",
                    "description": "Start timestamp in Unix milliseconds",
                },
                "endAt": {
                    "type": "integer",
                    "description": "End timestamp in Unix milliseconds",
                },
                "range": {
                    "type": "string",
                    "enum": ["last_24h", "last_7d", "last_30d", "this_month", "last_month"],
                    "description": RANGE_DESCRIPTION,
                },
                "compare": {
                    "type": "string",
                    "enum": ["prev", "yoy"],
                    "description": "Compare with previous period ('prev') or year-over-year ('yoy')",
                },
                **{
                    p["name"]: {"type": "string", "description": p["description"]}
                    for p in FILTER_PARAMS
                },
            },
            "required": ["websiteId"],
        },
    },
    {
        "name": "get_pageviews",
        "description": (
            "Get time-series pageview and session data for a website, bucketed by the chosen time unit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "websiteId": {"type": "string", "description": "Website UUID"},
                "startAt": {
                    "type": "integer",
                    "description": "Start timestamp in Unix milliseconds",
                },
                "endAt": {
                    "type": "integer",
                    "description": "End timestamp in Unix milliseconds",
                },
                "range": {
                    "type": "string",
                    "enum": ["last_24h", "last_7d", "last_30d", "this_month", "last_month"],
                    "description": RANGE_DESCRIPTION,
                },
                "unit": {
                    "type": "string",
                    "enum": ["minute", "hour", "day", "month", "year"],
                    "description": "Time bucket granularity",
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone for bucketing (e.g. 'America/New_York', 'UTC')",
                },
                "compare": {
                    "type": "string",
                    "enum": ["prev", "yoy"],
                    "description": "Compare with previous period ('prev') or year-over-year ('yoy')",
                },
                **{
                    p["name"]: {"type": "string", "description": p["description"]}
                    for p in FILTER_PARAMS
                },
            },
            "required": ["websiteId", "unit", "timezone"],
        },
    },
    {
        "name": "get_metrics",
        "description": (
            "Get a breakdown of metrics by a given dimension (url, referrer, browser, os, "
            "device, country, event, etc.) for a website."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "websiteId": {"type": "string", "description": "Website UUID"},
                "startAt": {
                    "type": "integer",
                    "description": "Start timestamp in Unix milliseconds",
                },
                "endAt": {
                    "type": "integer",
                    "description": "End timestamp in Unix milliseconds",
                },
                "range": {
                    "type": "string",
                    "enum": ["last_24h", "last_7d", "last_30d", "this_month", "last_month"],
                    "description": RANGE_DESCRIPTION,
                },
                "type": {
                    "type": "string",
                    "enum": [
                        "path",
                        "url",
                        "entry",
                        "exit",
                        "referrer",
                        "domain",
                        "title",
                        "query",
                        "event",
                        "tag",
                        "hostname",
                        "browser",
                        "os",
                        "device",
                        "screen",
                        "language",
                        "country",
                        "region",
                        "city",
                        "channel",
                    ],
                    "description": "Metric dimension to break down by",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 500)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of results to skip for pagination",
                },
                **{
                    p["name"]: {"type": "string", "description": p["description"]}
                    for p in FILTER_PARAMS
                },
            },
            "required": ["websiteId", "type"],
        },
    },
    {
        "name": "get_active",
        "description": "Get the number of currently active visitors on a website (last 5 minutes).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "websiteId": {"type": "string", "description": "Website UUID"},
            },
            "required": ["websiteId"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def handle_get_websites(args: dict) -> object:
    params = {}
    for key in ("search", "page", "pageSize", "includeTeams"):
        if args.get(key) is not None:
            params[key] = args[key]
    return _api_get("/websites", params or None)


def handle_get_stats(args: dict) -> object:
    start_at, end_at = _resolve_time_range(args)
    params = {
        "startAt": start_at,
        "endAt": end_at,
        **_pick_filters(args),
    }
    if args.get("compare"):
        params["compare"] = args["compare"]
    return _api_get(f"/websites/{args['websiteId']}/stats", params)


def handle_get_pageviews(args: dict) -> object:
    start_at, end_at = _resolve_time_range(args)
    params = {
        "startAt": start_at,
        "endAt": end_at,
        "unit": args["unit"],
        "timezone": args["timezone"],
        **_pick_filters(args),
    }
    if args.get("compare"):
        params["compare"] = args["compare"]
    return _api_get(f"/websites/{args['websiteId']}/pageviews", params)


def handle_get_metrics(args: dict) -> object:
    start_at, end_at = _resolve_time_range(args)
    metric_type = args["type"]
    params = {
        "startAt": start_at,
        "endAt": end_at,
        "type": metric_type,
        **_pick_filters(args),
    }
    if args.get("limit") is not None:
        params["limit"] = args["limit"]
    if args.get("offset") is not None:
        params["offset"] = args["offset"]
    try:
        return _api_get(f"/websites/{args['websiteId']}/metrics", params)
    except urllib.error.HTTPError as e:
        # Umami versions differ on whether this dimension is named "url" or "path".
        if e.code == 400 and metric_type in {"url", "path"}:
            params["type"] = "path" if metric_type == "url" else "url"
            return _api_get(f"/websites/{args['websiteId']}/metrics", params)
        raise


def handle_get_active(args: dict) -> object:
    return _api_get(f"/websites/{args['websiteId']}/active")


TOOL_HANDLERS = {
    "get_websites": handle_get_websites,
    "get_stats": handle_get_stats,
    "get_pageviews": handle_get_pageviews,
    "get_metrics": handle_get_metrics,
    "get_active": handle_get_active,
}


# ---------------------------------------------------------------------------
# MCP protocol (JSON-RPC over stdio)
# ---------------------------------------------------------------------------

SERVER_INFO = {
    "name": "umami-mcp",
    "version": "1.0.0",
}

CAPABILITIES = {
    "tools": {},
}


def _make_response(req_id: object, result: object) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _make_error(req_id: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_request(msg: dict) -> dict | None:
    method = msg.get("method", "")
    req_id = msg.get("id")
    params = msg.get("params", {})

    # --- Lifecycle ---
    if method == "initialize":
        return _make_response(
            req_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": SERVER_INFO,
                "capabilities": CAPABILITIES,
            },
        )

    if method == "notifications/initialized":
        return None  # notification, no response

    if method == "ping":
        return _make_response(req_id, {})

    # --- Tool discovery ---
    if method == "tools/list":
        return _make_response(req_id, {"tools": TOOLS})

    # --- Tool execution ---
    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return _make_response(
                req_id,
                {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                },
            )
        try:
            result = handler(tool_args)
            return _make_response(
                req_id,
                {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                },
            )
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            return _make_response(
                req_id,
                {
                    "content": [
                        {"type": "text", "text": f"Umami API error {e.code}: {body}"}
                    ],
                    "isError": True,
                },
            )
        except Exception as e:
            return _make_response(
                req_id,
                {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            )

    # Unknown method
    if req_id is not None:
        return _make_error(req_id, -32601, f"Method not found: {method}")
    return None  # ignore unknown notifications


def main() -> None:
    if not UMAMI_API_KEY and not (UMAMI_USERNAME and UMAMI_PASSWORD):
        print(
            "Error: Set UMAMI_API_KEY (for Umami Cloud) or both UMAMI_USERNAME and "
            "UMAMI_PASSWORD (for self-hosted)",
            file=sys.stderr,
        )
        sys.exit(1)
    if not _is_cloud and not UMAMI_URL:
        print("Error: UMAMI_URL environment variable is required for self-hosted mode", file=sys.stderr)
        sys.exit(1)
    if _is_cloud and UMAMI_URL:
        host = urllib.parse.urlparse(_base_url()).netloc.lower()
        if host == "cloud.umami.is":
            print(
                "Warning: UMAMI_URL points to cloud.umami.is. For Umami Cloud API, use "
                "https://api.umami.is (or leave UMAMI_URL unset).",
                file=sys.stderr,
            )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
