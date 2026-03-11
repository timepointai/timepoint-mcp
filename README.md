# timepoint-mcp

MCP server for the [Timepoint AI](https://timepointai.com) temporal knowledge platform.

**Domain:** `mcp.timepointai.com`

## What is this?

An MCP (Model Context Protocol) server that gives AI agents structured access to the Timepoint ecosystem:

- **Search & browse** a causal graph of 196+ historical moments spanning 2000+ years
- **Generate timepoints** — rich historical scenes with narratives, characters, dialog, and AI images
- **Navigate time** — step forward/backward from any moment to discover what came before and after
- **Chat with historical characters** — in-context conversations with period-appropriate personalities
- **Run simulations** — multi-entity temporal scenarios via the SNAG engine

Works with Claude Desktop, Cursor, Windsurf, VS Code Copilot, the Anthropic Agent SDK, and any MCP-compatible client.

## Quick start

### Claude Desktop

Add to `claude_desktop_config.json`:

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

### Local development (stdio)

```bash
git clone https://github.com/timepointai/timepoint-mcp.git
cd timepoint-mcp
pip install -e .
python -m app.server --transport stdio
```

## Tools

### Free tier (no credits required)

| Tool | Description |
|------|-------------|
| `search_moments` | Search the temporal causal graph for historical events |
| `get_moment` | Get full detail for a historical moment by path |
| `browse_graph` | Browse the temporal graph hierarchy (year/month/day/location) |
| `get_connections` | Get causal and thematic connections for a moment |
| `today_in_history` | Get events that happened on today's date |
| `random_moment` | Get a random historical moment for serendipitous discovery |
| `graph_stats` | Get statistics about the temporal knowledge graph |

### Generation tier (credits required)

| Tool | Credits | Description |
|------|---------|-------------|
| `generate_timepoint` | 5-10 | Generate a rich historical timepoint with scene, characters, dialog, image |
| `temporal_navigate` | 2 | Step forward/backward in time from an existing timepoint |
| `chat_with_character` | 1 | Converse with a historical character in context |
| `get_timepoint` | 0 | Retrieve a previously generated timepoint |
| `list_my_timepoints` | 0 | List your generated timepoints |
| `get_credit_balance` | 0 | Check credits and usage |

### Simulation tier (credits required)

| Tool | Credits | Description |
|------|---------|-------------|
| `run_simulation` | 10 | Run a SNAG temporal simulation |
| `get_simulation_result` | 0 | Get simulation results |

## Pricing

| Tier | Price | Monthly Credits | Rate Limit |
|------|-------|----------------|------------|
| Free | $0 | 5 signup credits | 30 req/min |
| Explorer | $7.99/mo | 100 | 60 req/min |
| Creator | $19.99/mo | 300 | 300 req/min |
| Studio | $49.99/mo | 1,000 | 1,000 req/min |

Credit packs also available as one-time purchases.

Anonymous access (no API key) is available for read-only clockchain tools at 30 req/min.

## Architecture

```
MCP Clients (Claude, Cursor, agents)
        │
        │ Streamable HTTP + API key
        ▼
   timepoint-mcp
   mcp.timepointai.com
        │
   ┌────┼────┬────────┐
   ▼    ▼    ▼        ▼
 Clock  Flash Billing  Pro
 chain        (Stripe) (SNAG)
```

The MCP server is a thin coordination layer. It authenticates requests, resolves user tiers via Billing, checks credit balance via Flash, routes tool calls to the appropriate backend service, and enforces rate limits.

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run locally with stdio transport
python -m app.server --transport stdio

# Run locally with HTTP transport
python -m app.server --transport http --port 8000

# Run tests
pytest
```

## Environment variables

```bash
FLASH_URL=https://api.timepointai.com
FLASH_SERVICE_KEY=...
FLASH_ADMIN_KEY=...
CLOCKCHAIN_URL=...
CLOCKCHAIN_SERVICE_KEY=...
BILLING_URL=...
BILLING_SERVICE_KEY=...
DATABASE_URL=postgresql://...
```

## License

Proprietary. Copyright 2026 Timepoint AI.
