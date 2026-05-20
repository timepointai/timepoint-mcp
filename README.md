# timepoint-mcp

MCP server for the [Timepoint AI](https://timepointai.com) temporal knowledge platform.

**Live at:** [`mcp.timepointai.com`](https://mcp.timepointai.com)

## What is this?

A hosted [Model Context Protocol](https://modelcontextprotocol.io) server that gives AI agents structured access to the Timepoint ecosystem:

- **Search & browse** a causal graph of 3,900+ historical moments and 5M+ edges spanning 700 BCE to 2026
- **Generate moments** — rich historical scenes rendered by the Flash reality-writing engine
- **Publish moments** — promote your private moments into the public clockchain
- **Index TDF records** — load pre-formatted Timepoint Data Format records directly (admin)

Planned: temporal navigation, character chat, and multi-entity SNAG simulations.

Works with Claude Desktop, Cursor, Windsurf, VS Code Copilot, the Anthropic Agent SDK, and any MCP-compatible client.

## Get an API key

Visit [timepointai.com](https://timepointai.com) or reach out on [X @timepointai](https://x.com/timepointai) to request access.

Clockchain read tools (search, browse, moment detail) work without authentication, rate-limited at 30 req/min. Write tools require an API key with the appropriate scope, and generation also requires credits.

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

### Clockchain read tools — live now

No authentication required; anonymous callers are rate-limited.

| Tool | Description |
|------|-------------|
| `search_moments` | Search the temporal causal graph for historical events |
| `get_moment` | Get full detail for a historical moment by its canonical path |
| `browse_graph` | Browse the graph hierarchy — year, month, day, location, event |
| `get_connections` | Get causal/thematic connections: what caused this, what it caused |
| `today_in_history` | Events that happened on today's date across all eras |
| `random_moment` | A random historical moment for serendipitous discovery |
| `graph_stats` | Node/edge counts, date range, source distribution |

### Write tools — live now

Require an API key with the listed scope.

| Tool | Scope | Credits | Description |
|------|-------|---------|-------------|
| `generate_moment` | `generate` | 5-10 | Generate a historical moment with Flash. Presets: `balanced` (5), `hd` (10), `hyper` (5), `gemini3` (5) |
| `publish_moment` | `generate` | 0 | Publish one of your private moments into the public clockchain |
| `index_moment_from_tdf` | `admin` | 0 | Index a pre-formatted TDF record directly into the clockchain |

### Planned

- **Temporal navigation** — step forward/backward in time from an existing moment
- **Character chat** — converse with historical characters in context
- **Simulations** — multi-entity temporal scenarios via the SNAG engine

## Pricing

| Tier | Price | Monthly Credits | Rate Limit |
|------|-------|----------------|------------|
| Anonymous | Free | — | 30 req/min (read-only) |
| Free | Free | 5 signup credits | 60 req/min |
| Explorer | $7.99/mo | 100 | 60 req/min |
| Creator | $19.99/mo | 300 | 300 req/min |
| Studio | $49.99/mo | 1,000 | 1,000 req/min |

Credit packs are also available as one-time purchases.

## HTTP endpoints

In addition to the MCP protocol at `/mcp`, the server exposes:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Landing page (JSON for agents, redirect to timepointai.com for browsers) |
| GET | `/health` | Service health check |
| GET | `/account/status` | Auth status and resolved tier |
| POST | `/admin/create-key` | Create an API key (requires `X-Admin-Key`) |

## Architecture

```
MCP Clients (Claude Desktop, Cursor, agents, SDKs)
        |
        | Streamable HTTP + X-API-Key
        v
   timepoint-mcp (mcp.timepointai.com)
   FastMCP + Starlette + asyncpg
        |
   -----+----------+-------------+----------+
   |               |             |          |
   v               v             v          v
 Clockchain      Flash      API Gateway   Billing
 (graph)        (writer)     (credits)    (tiers)
```

The MCP server is a thin coordination layer. It authenticates requests via API keys,
resolves user tiers via Billing, checks and spends credits via the API Gateway,
routes tool calls to the appropriate backend, and enforces per-tier rate limits. It
never stores credits or subscriptions — the Gateway and Billing own those.

## Tech stack

- **Python 3.11+** with FastMCP, Starlette, httpx, asyncpg, uvicorn
- **Transport:** Streamable HTTP (production), stdio (local dev)
- **Database:** PostgreSQL (API keys + usage logs)
- **Deployment:** Railway (Docker)

## Environment variables

```bash
# Downstream services
FLASH_URL=https://flash.timepointai.com
FLASH_OUTBOUND_KEY=...        # key sent to Flash as X-Service-Key (legacy alias: FLASH_SERVICE_KEY)
FLASH_ADMIN_KEY=...           # admin key gating POST /admin/create-key
CLOCKCHAIN_URL=...
CLOCKCHAIN_SERVICE_KEY=...
BILLING_URL=...
BILLING_SERVICE_KEY=...
GATEWAY_URL=...               # API Gateway — owns the credit ledger
GATEWAY_SERVICE_KEY=...

# Database
DATABASE_URL=postgresql://...  # API keys + usage logs; runs anonymous-only if unset

# Server
PORT=8000                      # honored by the Docker CMD (Railway sets this)
MCP_HOST=0.0.0.0               # defaults to 0.0.0.0; MCP_PORT defaults to 8000
MCP_SIGNING_SECRET=...         # request-signing secret
```


## Timepoint Suite

Render the past. Simulate the future. Score the predictions. Accumulate the graph.

| Service | Type | Repo | Role |
|---------|------|------|------|
| **API Gateway** | Private | timepoint-api-gateway | Auth authority — JWT, OAuth (Apple/Google/GitHub), credits, rate limiting at api.timepointai.com |
| **Flash** | Open Source | timepoint-flash | Reality Writer — pure generation engine (no auth), renders grounded historical moments |
| **Clockchain** | Open Source | timepoint-clockchain | Temporal Causal Graph — 3,900+ nodes, 5M+ edges, MCP endpoint, growing 24/7 |
| **Pro** | Open Source | timepoint-pro | SNAG Simulation Engine — temporal simulation, TDF output, training data |
| **Proteus** | Open Source | proteus | Settlement Layer — prediction markets for Rendered Futures |
| **TDF** | Open Source | timepoint-tdf | Data Format — JSON-LD interchange across all services |
| **SNAG Bench** | Open Source | timepoint-snag-bench | Quality Certifier — measures Causal Resolution across renderings |
| **Billing** | Private | timepoint-billing | Payment Processing — Apple IAP + Stripe |
| **MCP** | **Public** | **timepoint-mcp** | **MCP Server — AI agent access to Flash and Clockchain** |
| **Web App** | Private | timepoint-web-app | Browser client at app.timepointai.com |
| **Landing** | Private | timepoint-landing | Marketing site at timepointai.com |
| **iPhone App** | Private | timepoint-iphone-app | iOS client — Synthetic Time Travel on mobile |
| **Skip Meetings** | Private | skipmeetingsai | Meeting intelligence SaaS powered by Flash |

## License

Proprietary. Copyright 2026 Timepoint AI.
