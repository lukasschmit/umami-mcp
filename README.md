# Umami MCP Server

An MCP server for [Umami Analytics](https://umami.is) — works with both **Umami Cloud** and **self-hosted** instances.

**Zero dependencies.** No cloning, no install steps — just point your MCP client at it.

## Why?

Existing Umami MCP servers either [don't support Umami Cloud](https://github.com/Macawls/umami-mcp-server) (which uses API key auth, not username/password) or are [broken and bloated](https://github.com/jakeyShakey/umami_mcp_server) (torch, faiss, sentence-transformers for… analytics?).

This server talks to the Umami API and exposes 5 tools over MCP. Pure Python, zero dependencies.

## Tools

| Tool | Description |
|------|-------------|
| `get_websites` | List all tracked websites |
| `get_stats` | Summary stats: pageviews, visitors, visits, bounces, totaltime (seconds) |
| `get_pageviews` | Time-series pageview/session data (unit: minute/hour/day/month/year; timezone: IANA, e.g. UTC) |
| `get_metrics` | Breakdown by type: path/url/entry/exit/referrer/domain/title/query/event/tag/hostname/browser/os/device/screen/language/country/region/city/channel |
| `get_active` | Number of currently active visitors (last 5 minutes) |

## Quick Start

### 1. Get your credentials

**Umami Cloud:** Go to Settings → API Keys in your [Umami Cloud dashboard](https://cloud.umami.is) and create an API key.

**Self-hosted:** Use the username and password you log in with.

### 2. Add to your MCP client

No cloning required — `uvx` fetches and runs it directly from GitHub.

> **Requires [`uv`](https://docs.astral.sh/uv/getting-started/installation/).** Install with: `curl -LsSf https://astral.sh/uv/install.sh | sh`

#### Claude Desktop / Claude Code

Add to your MCP config (`~/.claude.json`, Claude Desktop settings, etc.):

**Umami Cloud:**
```json
{
  "mcpServers": {
    "umami": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lukasschmit/umami-mcp", "umami-mcp"],
      "env": {
        "UMAMI_URL": "https://api.umami.is",
        "UMAMI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

**Self-hosted:**
```json
{
  "mcpServers": {
    "umami": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lukasschmit/umami-mcp", "umami-mcp"],
      "env": {
        "UMAMI_URL": "https://your-umami-instance.com",
        "UMAMI_USERNAME": "admin",
        "UMAMI_PASSWORD": "your_password"
      }
    }
  }
}
```

#### Cursor

Add to `.cursor/mcp.json` in your project root (or global settings):

```json
{
  "mcpServers": {
    "umami": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lukasschmit/umami-mcp", "umami-mcp"],
      "env": {
        "UMAMI_URL": "https://api.umami.is",
        "UMAMI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

#### VS Code (Copilot)

Add to your VS Code `settings.json`:

```json
{
  "mcp": {
    "servers": {
      "umami": {
        "command": "uvx",
        "args": ["--from", "git+https://github.com/lukasschmit/umami-mcp", "umami-mcp"],
        "env": {
          "UMAMI_URL": "https://api.umami.is",
          "UMAMI_API_KEY": "your_api_key_here"
        }
      }
    }
  }
}
```

#### BoltAI

Go to Settings → MCP Servers → Add Server, then enter:

- **Command:** `uvx`
- **Arguments:** `--from git+https://github.com/lukasschmit/umami-mcp umami-mcp`
- **Environment Variables:**
  - `UMAMI_URL` = `https://api.umami.is`
  - `UMAMI_API_KEY` = `your_api_key_here`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `UMAMI_URL` | Self-hosted: Yes, Cloud: Optional | Base URL — defaults to `https://api.umami.is` in Cloud mode |
| `UMAMI_API_KEY` | Cloud | API key from Umami Cloud dashboard |
| `UMAMI_USERNAME` | Self-hosted | Login username |
| `UMAMI_PASSWORD` | Self-hosted | Login password |
| `UMAMI_CF_ACCESS_CLIENT_ID` | Optional | Cloudflare Access service token client ID (for protected self-hosted APIs) |
| `UMAMI_CF_ACCESS_CLIENT_SECRET` | Optional | Cloudflare Access service token secret |
| `UMAMI_USER_AGENT` | Optional | Custom User-Agent for outbound requests (default: `umami-mcp/1.0`) |
| `UMAMI_DEBUG` | Optional | Set to `1`/`true` to log outbound request URLs to stderr for debugging |

Set either `UMAMI_API_KEY` (Cloud) or both `UMAMI_USERNAME` + `UMAMI_PASSWORD` (self-hosted). The server auto-detects which mode to use.
For convenience, `UMAMI_URL` may include `/v1` (Cloud) or `/api` (self-hosted); suffixes are normalized automatically.

If your self-hosted Umami is behind Cloudflare Access, set both `UMAMI_CF_ACCESS_CLIENT_ID` and `UMAMI_CF_ACCESS_CLIENT_SECRET` so machine-to-machine MCP calls can pass Access checks.

`get_metrics` accepts both `type="path"` and `type="url"` for compatibility across Umami versions.
`startAt` and `endAt` accept Unix-millisecond integers or numeric strings from MCP clients.
For time-based tools, you can use `range` instead of raw timestamps:
`last_24h`, `last_7d`, `last_30d`, `this_month`, `last_month`.
`compare` supports `prev` (previous period, same length) and `yoy` (year-over-year).

## Usage Examples

Once connected, you can ask your AI assistant things like:

- *"What are my top pages this week?"*
- *"Show me visitor trends for the last 30 days"*
- *"Which countries are my visitors from?"*
- *"How many people are on my site right now?"*
- *"Compare this month's traffic to last month"*

The assistant will call the appropriate tools with the right parameters.

## How It Works

The server implements the [Model Context Protocol](https://modelcontextprotocol.io/) over stdio (JSON-RPC, one JSON object per line). When an MCP client starts it, the server:

1. Reads JSON-RPC messages from stdin
2. Handles `initialize`, `tools/list`, and `tools/call` methods
3. Makes authenticated HTTP requests to the Umami API
4. Returns results as JSON text content

No background processes, no polling, no state beyond the auth token.

## License

MIT
