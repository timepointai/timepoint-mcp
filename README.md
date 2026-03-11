# timepoint-mcp

MCP server for the [Timepoint AI](https://timepointai.com) temporal knowledge platform.

**Live at:** [`mcp.timepointai.com`](https://mcp.timepointai.com)

## What is this?

A hosted [Model Context Protocol](https://modelcontextprotocol.io) server that gives AI agents structured access to the Timepoint ecosystem:

- **Search & browse** a causal graph of 196+ historical moments spanning 2000+ years
- **Generate timepoints** — rich historical scenes with narratives, characters, dialog, and AI images (coming soon)
- **Navigate time** — step forward/backward from any moment to discover what came before and after (coming soon)
- **Chat with historical characters** — in-context conversations with period-appropriate personalities (coming soon)
- **Run simulations** — multi-entity temporal scenarios via the SNAG engine (coming soon)

Works with Claude Desktop, Cursor, Windsurf, VS Code Copilot, the Anthropic Agent SDK, and any MCP-compatible client.

## Get an API key

Visit [timepointai.com](https://timepointai.com) or reach out on [X @timepointai](https://x.com/timepointai) to request access.

Clockchain read tools (search, browse, moment detail) work without authentication at 30 req/min. Generation and simulation tools require an API key and credits.

## Quick start

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "timepoint": {
      "url": "https://mcp.timepointai.com/mcp",
      "headers": {
        "X-API-Key": "tp_mcp_..."
      }
    }
  }
}
```

### Cursor / Windsurf

Add to `.cursor/mcp.json` or equivalent:

```json
{
  "mcpServers": {
    "timepoint": {
      "url": "https://mcp.timepointai.com/mcp",
      "headers": {
        "X-API-Key": "tp_mcp_..."
      }
    }
  }
}
```

### Anthropic Agent SDK

```python
from claude_agent_sdk import Agent
from claude_agent_sdk.mcp import MCPServerRemote

agent = Agent(
    model="claude-sonnet-4-6",
    mcp_servers=[
        MCPServerRemote(
            url="https://mcp.timepointai.com/mcp",
            headers={"X-API-Key": "tp_mcp_..."},
        )
    ],
)
result = agent.run("What happened in Rome in 44 BC?")
```

### Local development

```bash
git clone https://github.com/timepointai/timepoint-mcp.git
cd timepoint-mcp
pip install -e .

# stdio transport (for Claude Desktop local)
python -m app.server --transport stdio

# HTTP transport (for remote testing)
python -m app.server --transport http --port 8000
```

## Available tools

### Phase 1 (live now) — Clockchain read tools

| Tool | Auth | Description |
|------|------|-------------|
| `search_moments` | Optional | Search the temporal causal graph for historical events |
| `get_moment` | Optional | Get full detail for a historical moment by its canonical path |
| `browse_graph` | Optional | Browse the graph hierarchy — year, month, day, location, event |
| `get_connections` | Optional | Get causal/thematic connections: what caused this, what it caused |
| `today_in_history` | Key | Events that happened on today's date across all eras |
| `random_moment` | Key | Random historical moment for serendipitous discovery |
| `graph_stats` | Optional | Node/edge counts, date range, source distribution |

### Phase 2 (coming soon) — Generation tools

| Tool | Credits | Description |
|------|---------|-------------|
| `generate_timepoint` | 5-10 | Generate a historical timepoint with scene, characters, dialog, image |
| `temporal_navigate` | 2 | Step forward/backward in time from an existing timepoint |
| `chat_with_character` | 1 | Converse with a historical character in context |
| `get_timepoint` | 0 | Retrieve a previously generated timepoint |
| `list_my_timepoints` | 0 | List your generated timepoints |
| `get_credit_balance` | 0 | Check credits and usage |

### Phase 3 (planned) — Simulation tools

| Tool | Credits | Description |
|------|---------|-------------|
| `run_simulation` | 10 | Run a SNAG temporal simulation |
| `get_simulation_result` | 0 | Get simulation results |

## Pricing

| Tier | Price | Monthly Credits | Rate Limit |
|------|-------|----------------|------------|
| Anonymous | Free | — | 30 req/min (read-only) |
| Free | Free | 5 signup credits | 60 req/min |
| Explorer | $7.99/mo | 100 | 60 req/min |
| Creator | $19.99/mo | 300 | 300 req/min |
| Studio | $49.99/mo | 1,000 | 1,000 req/min |

Credit packs also available as one-time purchases.

## HTTP endpoints

In addition to the MCP protocol at `/mcp`, the server exposes:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Landing page (JSON for agents, redirect for browsers) |
| GET | `/health` | Service health check |
| GET | `/account/status` | Auth status and tier info |
| POST | `/admin/create-key` | Create API key (requires admin key) |

## Architecture

```
MCP Clients (Claude Desktop, Cursor, agents, SDKs)
        |
        | Streamable HTTP + X-API-Key
        v
   timepoint-mcp (mcp.timepointai.com)
   FastMCP + Starlette + asyncpg
        |
   -----+------+----------+
   |           |           |
   v           v           v
 Clockchain  Flash      Billing
 (graph)    (writer)   (Stripe/IAP)
```

The MCP server is a thin coordination layer. It authenticates requests via API keys, resolves user tiers via Billing, checks credit balance via Flash, routes tool calls to the appropriate backend, and enforces per-tier rate limits. It never stores credits or subscriptions — Flash and Billing own those.

## Tech stack

- **Python 3.11+** with FastMCP, Starlette, httpx, asyncpg
- **Transport:** Streamable HTTP (production), stdio (local dev)
- **Database:** PostgreSQL (API keys + usage logs)
- **Deployment:** Railway (Docker)

## Environment variables

```bash
# Downstream services
FLASH_URL=https://api.timepointai.com
FLASH_SERVICE_KEY=...
FLASH_ADMIN_KEY=...
CLOCKCHAIN_URL=...
CLOCKCHAIN_SERVICE_KEY=...
BILLING_URL=...
BILLING_SERVICE_KEY=...

# Database
DATABASE_URL=postgresql://...

# Server
PORT=8000
```

## License

Proprietary. Copyright 2026 Timepoint AI.
