# Timepoint MCP — Ecosystem Context for Coding Agents

This document provides the full context a coding agent needs to build and maintain the Timepoint MCP server.

---

## Service Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                     TIMEPOINT ECOSYSTEM                              │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  MCP Server (this repo)          mcp.timepointai.com         │   │
│  │  FastMCP + Streamable HTTP                                    │   │
│  │  API key auth → tier resolution → credit check → tool exec   │   │
│  └────┬──────────┬──────────┬───────────────────────────────────┘   │
│       │          │          │                                        │
│       ▼          ▼          ▼                                        │
│  ┌─────────┐ ┌────────┐ ┌────────┐                                 │
│  │Clockchn │ │ Flash  │ │Billing │                                 │
│  │ Graph   │ │ Writer │ │ Stripe │                                 │
│  │ DB+API  │ │ 14-agt │ │ Apple  │                                 │
│  └─────────┘ └────────┘ └────────┘                                 │
│       │          │          │                                        │
│       └──────────┴──────────┘                                        │
│              shared PostgreSQL                                       │
│              (separate DBs)                                          │
│                                                                      │
│  Also: Proteus (prediction markets, future), TDF (data format lib), │
│  SNAG-Bench (quality benchmarks), Landing (timepointai.com),         │
│  Web App (app.timepointai.com), iPhone App                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## How to Call Each Service

### Flash (api.timepointai.com)

The main backend. Handles generation, auth, credits, user management.

**Auth headers for service calls:**
```
X-Service-Key: {FLASH_SERVICE_KEY}       # machine-to-machine auth
X-User-ID: {user_id}                      # forwarded user identity (optional)
X-Admin-Key: {FLASH_ADMIN_KEY}           # admin operations (credit grants)
```

**Endpoints the MCP server calls:**

| Purpose | Method | Path | Headers | Notes |
|---------|--------|------|---------|-------|
| Find/create user | POST | `/api/v1/users/resolve` | Service-Key | Body: `{external_id, email}` |
| Credit balance | GET | `/api/v1/credits/balance` | Service-Key + User-ID | |
| Credit costs | GET | `/api/v1/credits/costs` | Service-Key | |
| Generate sync | POST | `/api/v1/timepoints/generate/sync` | Service-Key + User-ID | Flash deducts credits |
| Generate stream | POST | `/api/v1/timepoints/generate/stream` | Service-Key + User-ID | SSE events |
| Get timepoint | GET | `/api/v1/timepoints/{id}` | Service-Key + User-ID | |
| List user TPs | GET | `/api/v1/users/me/timepoints` | Service-Key + User-ID | Paginated |
| Temporal next | POST | `/api/v1/temporal/{id}/next` | Service-Key + User-ID | |
| Temporal prior | POST | `/api/v1/temporal/{id}/prior` | Service-Key + User-ID | |
| Chat | POST | `/api/v1/{id}/chat` | Service-Key + User-ID | |
| Chat stream | POST | `/api/v1/{id}/chat/stream` | Service-Key + User-ID | SSE |

**Credit costs (hardcoded in Flash):**
- generate_balanced: 5, generate_hd: 10, generate_hyper: 5
- chat: 1, temporal_jump: 2

**Key detail:** When MCP passes `X-Service-Key` + `X-User-ID`, Flash resolves the user and deducts credits from *their* account. The MCP server never handles credit math — Flash is the single source of truth.

### Clockchain (via Flash proxy OR direct)

The temporal causal graph. 196+ nodes, 671+ edges, -133 BCE to 2019 CE.

**Via Flash proxy** (preferred for authenticated calls):
```
GET https://api.timepointai.com/api/v1/clockchain/search?q=rome
Headers: X-Service-Key: {FLASH_SERVICE_KEY}
```
Flash forwards to Clockchain with its own service key.

**Direct** (for anonymous/read-only):
```
GET https://{CLOCKCHAIN_URL}/api/v1/moments?q=rome&limit=20
```
Public endpoints need no auth. Authenticated endpoints need `X-Service-Key`.

**Endpoints:**

| Purpose | Method | Path | Auth |
|---------|--------|------|------|
| Search | GET | `/api/v1/search?q=` | Service-Key |
| List moments | GET | `/api/v1/moments` | Public (rate-limited) |
| Get moment | GET | `/api/v1/moments/{path}` | Public (public moments) |
| Browse | GET | `/api/v1/browse/{path}` | Service-Key |
| Today | GET | `/api/v1/today` | Service-Key |
| Random | GET | `/api/v1/random` | Service-Key |
| Neighbors | GET | `/api/v1/graph/neighbors/{path}` | Service-Key |
| Stats | GET | `/api/v1/stats` | Public |

**Write endpoints (used by MCP write tools):**

| Purpose | Method | Path | Auth |
|---------|--------|------|------|
| Index moment | POST | `/api/v1/index` | Service-Key |
| Update visibility | PATCH | `/api/v1/moments/{path}/visibility` | Service-Key |
| Ingest TDF | POST | `/api/v1/ingest/tdf` | Service-Key |

**Response shapes:**
- Moments include: `path, name, one_liner, year, month, day, country, region, city, tags, figures, image_url, edges[], schema_version`
- v0.2 moments also include: `text_model, image_model, model_provider, model_permissiveness, generation_id, graph_state_hash`
- Search results: `path, name, one_liner, score, image_url`
- Browse items: `segment, count, label`
- Stats: `total_nodes, total_edges, nodes_with_images, layer_counts, edge_type_counts, date_range`
- Edge types (v0.2): `causes, caused_by, influences, contemporaneous, same_location, same_era, same_conflict, same_figure, thematic, precedes, follows`
- Edges include: `type, target_path, description, created_by, schema_version`

### Billing (billing.timepointai.com)

Manages Stripe + Apple IAP subscriptions and credit packs.

**Auth:** `X-Service-Key: {BILLING_SERVICE_KEY}`

**Endpoints the MCP server calls:**

| Purpose | Method | Path | Headers |
|---------|--------|------|---------|
| User tier/status | GET | `/internal/billing/status` | Service-Key + X-User-Id |
| Product catalog | GET | `/internal/billing/products` | (public) |
| Stripe checkout | POST | `/internal/billing/stripe/checkout` | Service-Key + X-User-Id |
| Stripe portal | GET | `/internal/billing/stripe/portal` | Service-Key + X-User-Id |

**Tier resolution:**
- Response: `{subscription_tier, status, period_end, credits_per_period}`
- No subscription row = free tier
- `status` in: `active`, `canceled`, `past_due`, `expired`
- Only `active` counts as subscribed; all others = free tier for rate limit purposes

---

## Data Flow for Key Operations

### generate_timepoint (5 credits)

```
1. Agent calls generate_timepoint(query="Fall of Rome", preset="balanced")
2. MCP resolves user_id from API key (mcp_api_keys table)
3. MCP calls Billing: GET /internal/billing/status → tier for rate limit check
4. MCP calls Flash: GET /api/v1/credits/balance → verify >= 5 credits
5. MCP calls Flash: POST /api/v1/timepoints/generate/sync
     Headers: X-Service-Key + X-User-ID
     Body: {query, preset, visibility}
6. Flash runs 14-agent pipeline (15-60 seconds)
7. Flash deducts 5 credits internally
8. Flash returns TimepointResponse
9. MCP extracts key fields, adds credits_remaining
10. MCP returns result to agent
```

### search_moments (free)

```
1. Agent calls search_moments(query="ancient rome", limit=10)
2. MCP checks rate limit for this API key's tier
3. MCP calls Clockchain: GET /api/v1/search?q=ancient+rome
     (direct or via Flash proxy)
4. MCP returns results to agent
```

### Anonymous search (no API key)

```
1. Agent calls search_moments(query="rome") with no auth
2. MCP applies anonymous rate limit (30 req/min by IP)
3. MCP calls Clockchain public endpoint directly
4. Returns results
```

---

## MCP API Key System

The MCP server manages its own API keys (Flash and Billing have no concept of MCP keys).

**Key format:** `tp_mcp_<32 hex chars>` (e.g., `tp_mcp_a1b2c3d4e5f6...`)

**Storage:** PostgreSQL table `mcp_api_keys`:
```sql
CREATE TABLE mcp_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash TEXT NOT NULL UNIQUE,     -- SHA-256 of full key
    key_prefix TEXT NOT NULL,          -- "tp_mcp_a1b2" for display
    user_id TEXT NOT NULL,             -- Flash user_id
    name TEXT NOT NULL,                -- user label
    scopes TEXT[] DEFAULT '{read}',    -- read, generate, simulate, admin
    created_at TIMESTAMPTZ DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    rate_limit INT DEFAULT 60,
    write_rate_limit INT DEFAULT 10
);
```

**Key → user_id mapping:** When a request arrives with `X-API-Key`, the MCP server hashes it, looks up the row, gets `user_id`. That `user_id` is then used in all downstream calls (`X-User-ID` header to Flash, `X-User-Id` header to Billing).

**Provisioning:** Keys are created via `POST /account/keys` which requires a Bearer JWT from Flash (obtained via Apple Sign-In or dev token).

---

## Freemium Tiers

| | Free | Explorer | Creator | Studio |
|---|---|---|---|---|
| Price | $0 | $7.99/mo | $19.99/mo | $49.99/mo |
| Monthly credits | 5 (signup) | 100 | 300 | 1,000 |
| Rate limit | 30 req/min | 60 req/min | 300 req/min | 1,000 req/min |
| Concurrent | 2 | 5 | 20 | 50 |
| Daily cap | 500 | 2,000 | 50,000 | unlimited |
| API keys | 1 | 3 | 10 | 25 |
| Clockchain read | Yes | Yes | Yes | Yes |
| Generation | Yes* | Yes | Yes | Yes |
| SSE streaming | No | Yes | Yes | Yes |

*Free tier can generate until credits run out (5 signup credits = 1 balanced generation).

Tier is determined by querying Billing's `/internal/billing/status`. No subscription row = free.

---

## Technology Stack

- **Language:** Python 3.12+
- **MCP framework:** FastMCP >= 2.0
- **Transport:** Streamable HTTP (production), stdio (local dev)
- **HTTP client:** httpx (async)
- **Database:** PostgreSQL via asyncpg (API keys + usage logs)
- **Validation:** Pydantic v2
- **Config:** pydantic-settings (env vars)
- **Deployment:** Railway (Dockerfile)
- **Domain:** mcp.timepointai.com

---

## Environment Variables

```
# Downstream services
FLASH_URL=https://api.timepointai.com
FLASH_SERVICE_KEY=<flash-service-key>
FLASH_ADMIN_KEY=<flash-admin-key>
CLOCKCHAIN_URL=<clockchain-url>
CLOCKCHAIN_SERVICE_KEY=<clockchain-service-key>
BILLING_URL=<billing-url>
BILLING_SERVICE_KEY=<billing-service-key>

# MCP server
MCP_HOST=0.0.0.0
MCP_PORT=8000
DATABASE_URL=postgresql://...
MCP_SIGNING_SECRET=<secret>
```

---

## Related Repos

| Repo | Role | URL |
|------|------|-----|
| timepoint-flash | Main API + generation engine | github.com/timepointai/timepoint-flash |
| timepoint-clockchain | Temporal causal graph | github.com/timepointai/timepoint-clockchain |
| timepoint-billing | Stripe/Apple IAP billing | (private) |
| timepoint-tdf | Data interchange format | github.com/timepointai/timepoint-tdf |
| timepoint-web-app | Web frontend | (private) |
| timepoint-iphone-app | iOS app | (private) |
| proteus | Prediction markets | github.com/timepointai/proteus |
| timepoint-snag-bench | Quality benchmarks | github.com/timepointai/timepoint-snag-bench |
| timepoint-landing | Landing page | (private) |
| timepoint-dev-management | Ops/management | (private) |
