# Umami MCP Server

An MCP server for [Umami Analytics](https://umami.is) — works with both **Umami Cloud** and **self-hosted** instances.

**Zero dependencies.** Pure Python, single file, just run it.

## Why?

Existing Umami MCP servers either [don't support Umami Cloud](https://github.com/Macawls/umami-mcp-server) (which uses API key auth, not username/password) or are [broken and bloated](https://github.com/jakeyShakey/umami_mcp_server) (torch, faiss, sentence-transformers for… analytics?).

This server is a single Python file that talks to the Umami API and exposes 5 tools over MCP.

## Tools

| Tool | Description |
|------|-------------|
| `get_websites` | List all tracked websites |
| `get_stats` | Summary stats: pageviews, visitors, bounces, time on site |
| `get_pageviews` | Time-series pageview data (bucketed by minute/hour/day/month/year) |
| `get_metrics` | Breakdown by URL, referrer, browser, OS, device, country, event, etc. |
| `get_active` | Number of currently active visitors (last 5 minutes) |

## Setup

### 1. Get your credentials

**Umami Cloud:** Go to Settings → API Keys in your [Umami Cloud dashboard](https://cloud.umami.is) and create an API key.

**Self-hosted:** Use the username and password you log in with.

### 2. Configure your MCP client

#### Claude Desktop / Claude Code

Add to your MCP config (`~/.claude.json`, Claude Desktop settings, etc.):

**Umami Cloud:**
```json
{
  "mcpServers": {
    "umami": {
      "command": "python3",
      "args": ["/absolute/path/to/server.py"],
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
      "command": "python3",
      "args": ["/absolute/path/to/server.py"],
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
      "command": "python3",
      "args": ["/absolute/path/to/server.py"],
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
        "command": "python3",
        "args": ["/absolute/path/to/server.py"],
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

- **Command:** `python3`
- **Arguments:** `/absolute/path/to/server.py`
- **Environment Variables:**
  - `UMAMI_URL` = `https://api.umami.is`
  - `UMAMI_API_KEY` = `your_api_key_here`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `UMAMI_URL` | Yes | Base URL — `https://api.umami.is` for Cloud, or your self-hosted URL |
| `UMAMI_API_KEY` | Cloud | API key from Umami Cloud dashboard |
| `UMAMI_USERNAME` | Self-hosted | Login username |
| `UMAMI_PASSWORD` | Self-hosted | Login password |

Set either `UMAMI_API_KEY` (Cloud) or both `UMAMI_USERNAME` + `UMAMI_PASSWORD` (self-hosted). The server auto-detects which mode to use.

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
