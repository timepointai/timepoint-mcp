# Timepoint MCP Server — Implementation Plan

## Phase 1: Clockchain Read + Auth Foundation

**Goal:** 7 read-only tools, API key auth, anonymous + free tiers, deployed at mcp.timepointai.com.

### Step 1.1: Project scaffolding

- [ ] `pyproject.toml` with dependencies: fastmcp, httpx, asyncpg, pydantic, pydantic-settings, uvicorn
- [ ] `Dockerfile` (python:3.12-slim, pip install, uvicorn entrypoint)
- [ ] `app/__init__.py`
- [ ] `app/config.py` — pydantic-settings `Settings` class with all env vars
- [ ] `app/server.py` — FastMCP init, Streamable HTTP transport, `/health` endpoint

### Step 1.2: Database + API key auth

- [ ] `app/auth/__init__.py`
- [ ] `app/auth/keys.py` — `mcp_api_keys` table DDL, `create_key()`, `validate_key()`, `revoke_key()`
- [ ] `app/auth/middleware.py` — extract API key from `X-API-Key` header, resolve user_id, attach to request context
- [ ] Schema init on startup (CREATE TABLE IF NOT EXISTS)
- [ ] Anonymous fallback — if no key, allow read tools with anonymous rate limit

### Step 1.3: Rate limiting

- [ ] In-memory sliding window rate limiter (upgrade to Redis later)
- [ ] Per-key limits based on tier (default: free=30/min)
- [ ] Anonymous limit by client IP (30/min)
- [ ] Return `429 Too Many Requests` with `Retry-After` header

### Step 1.4: Clockchain client

- [ ] `app/clients/__init__.py`
- [ ] `app/clients/clockchain.py` — `ClockchainClient` with httpx async
  - `search(query, limit)` → calls `GET /api/v1/search?q=`
  - `get_moment(path)` → calls `GET /api/v1/moments/{path}`
  - `browse(path)` → calls `GET /api/v1/browse/{path}`
  - `neighbors(path)` → calls `GET /api/v1/graph/neighbors/{path}`
  - `today()` → calls `GET /api/v1/today`
  - `random()` → calls `GET /api/v1/random`
  - `stats()` → calls `GET /api/v1/stats`
- [ ] Use direct Clockchain URL for public reads, Flash proxy for authenticated reads
- [ ] Error mapping: Clockchain HTTP errors → actionable MCP error messages

### Step 1.5: Clockchain tools

- [ ] `app/tools/__init__.py`
- [ ] `app/tools/clockchain.py` — 7 tools:
  - `search_moments(query, year_from?, year_to?, limit=20)`
  - `get_moment(path, format="default")`
  - `browse_graph(path="/")`
  - `get_connections(path)`
  - `today_in_history()`
  - `random_moment()`
  - `graph_stats()`
- [ ] Each tool: validate args → check rate limit → call client → format response
- [ ] Tool descriptions written for LLM consumption (specific about when/why to use)

### Step 1.6: Account endpoints (plain HTTP, not MCP)

- [ ] `POST /account/keys` — create API key (requires Bearer JWT from Flash)
- [ ] `GET /account/keys` — list keys (prefix + name + last_used)
- [ ] `DELETE /account/keys/{key_id}` — revoke key
- [ ] `GET /account/status` — tier, credits, key count

### Step 1.7: Deploy

- [ ] Push to GitHub
- [ ] Railway: connect repo, set env vars, add PostgreSQL
- [ ] Railway: custom domain `mcp.timepointai.com`
- [ ] Verify `/health` returns OK
- [ ] Test all 7 tools via Claude Desktop or curl

### Step 1.8: Tests

- [ ] `tests/test_tools_clockchain.py` — mock clockchain client, test each tool
- [ ] `tests/test_auth.py` — key creation, validation, revocation
- [ ] `tests/test_rate_limit.py` — verify limits enforced

---

## Phase 2: Flash Generation + Billing Integration

**Goal:** 6 generation/account tools, credit metering, tier-based rate limits, Stripe checkout.

### Step 2.1: Flash client

- [ ] `app/clients/flash.py` — `FlashClient`
  - `resolve_user(external_id, email)` → `POST /api/v1/users/resolve`
  - `get_balance(user_id)` → `GET /api/v1/credits/balance`
  - `get_costs()` → `GET /api/v1/credits/costs`
  - `generate_sync(query, preset, user_id)` → `POST /api/v1/timepoints/generate/sync`
  - `generate_stream(query, preset, user_id)` → `POST /api/v1/timepoints/generate/stream` (SSE)
  - `get_timepoint(id, user_id)` → `GET /api/v1/timepoints/{id}`
  - `list_user_timepoints(user_id, page, page_size)` → `GET /api/v1/users/me/timepoints`
  - `temporal_next(id, units, unit, user_id)` → `POST /api/v1/temporal/{id}/next`
  - `temporal_prior(id, units, unit, user_id)` → `POST /api/v1/temporal/{id}/prior`
  - `chat(id, character, message, session_id, user_id)` → `POST /api/v1/{id}/chat`

### Step 2.2: Billing client

- [ ] `app/clients/billing.py` — `BillingClient`
  - `get_status(user_id)` → `GET /internal/billing/status`
  - `get_products()` → `GET /internal/billing/products`
  - `create_checkout(user_id, product_id)` → `POST /internal/billing/stripe/checkout`
  - `get_portal(user_id)` → `GET /internal/billing/stripe/portal`

### Step 2.3: Credit metering middleware

- [ ] `app/billing/__init__.py`
- [ ] `app/billing/credits.py`
  - `check_credits(user_id, cost)` — calls Flash balance, returns bool + balance
  - Credit costs map: `{generate_balanced: 5, generate_hd: 10, generate_hyper: 5, chat: 1, temporal_jump: 2, simulation: 10}`
  - Insufficient credit errors include balance, cost, and upgrade URL

### Step 2.4: Tier resolution

- [ ] On every authenticated request, resolve tier:
  1. API key → user_id (from key store)
  2. user_id → billing status (cache for 60s)
  3. billing status → tier → rate limits
- [ ] Cache tier for 60 seconds to avoid hammering billing service
- [ ] Tier determines: rate limit, concurrent cap, daily cap, tool access, max API keys

### Step 2.5: Generation tools

- [ ] `app/tools/generation.py` — 4 tools:
  - `generate_timepoint(query, preset="balanced", visibility="private", stream=false)` [5-10 credits]
  - `temporal_navigate(timepoint_id, direction, units=1, unit="year")` [2 credits]
  - `chat_with_character(timepoint_id, character_name, message, session_id?)` [1 credit]
  - `get_timepoint(timepoint_id)`
- [ ] Each credited tool: check tier access → check balance → execute → return with credits_remaining

### Step 2.6: Account tools

- [ ] `app/tools/account.py` — 2 tools:
  - `list_my_timepoints(page=1, page_size=20, status?)`
  - `get_credit_balance()`
- [ ] Balance response includes upgrade prompt when low

### Step 2.7: Account HTTP endpoints

- [ ] `POST /account/checkout` — proxy to billing's Stripe checkout
- [ ] `GET /account/portal` — proxy to billing's Stripe portal
- [ ] Update `GET /account/status` to include tier, subscription info

### Step 2.8: Billing service changes

- [ ] Add MCP's service key to billing's allowed callers
- [ ] Create real Stripe products/prices (replace placeholders in products.py)
- [ ] Add `metadata.source = "mcp"` tracking on MCP-originated checkouts

### Step 2.9: Deploy + test

- [ ] Add env vars: BILLING_URL, BILLING_SERVICE_KEY
- [ ] Test generation flow end-to-end
- [ ] Test credit deduction
- [ ] Test tier-based rate limiting
- [ ] Test Stripe checkout flow

---

## Phase 3: Pro Simulations + OAuth 2.1

**Goal:** 2 simulation tools, OAuth 2.1 for native MCP client auth.

### Step 3.1: Pro client

- [ ] `app/clients/pro.py` — `ProClient`
  - `create_simulation(description, template, entity_count, temporal_mode)` → `POST /simulations/`
  - `get_result(job_id)` → `GET /simulations/{job_id}/result`
  - `list_templates()` → `GET /simulations/templates`

### Step 3.2: Simulation tools

- [ ] `app/tools/simulation.py` — 2 tools:
  - `run_simulation(description, template, entity_count=3, temporal_mode="linear")` [10 credits]
  - `get_simulation_result(job_id)`
- [ ] Gate behind Explorer+ tier (free tier cannot access)

### Step 3.3: OAuth 2.1

- [ ] `app/auth/oauth.py`
- [ ] Protected Resource Metadata at `/.well-known/oauth-protected-resource`
- [ ] Authorization server discovery (delegate to Flash's auth or standalone)
- [ ] PKCE flow support
- [ ] Token validation
- [ ] Scoped access (read, generate, simulate)

### Step 3.4: Key management web UI

- [ ] Coordinate with web app team to add `/settings/keys` page
- [ ] Web app calls MCP's `/account/keys` endpoints
- [ ] Show key prefix, name, last used, scopes
- [ ] Create/revoke from the UI

---

## Phase 4: Proteus Markets + Advanced Features

**Goal:** 2 market tools, usage analytics, metrics.

### Step 4.1: Proteus integration

- [ ] `app/clients/proteus.py` — `ProteusClient`
- [ ] `app/tools/markets.py` — 2 tools:
  - `browse_prediction_markets(status="active", limit=20)`
  - `get_market_detail(market_id)`
- [ ] Read-only, no credits required

### Step 4.2: MCP Resources

- [ ] `app/resources/static.py`
  - `timepoint://stats` → graph statistics
  - `timepoint://moment/{path}` → moment data
  - `timepoint://today` → today-in-history
  - `timepoint://models` → available AI models
  - `timepoint://credit-costs` → pricing table

### Step 4.3: MCP Prompts

- [ ] `app/prompts/templates.py`
  - `explore_era(era, focus?)` — guided exploration of a historical period
  - `generate_and_explore(query)` — generate then navigate temporal neighborhood
  - `character_interview(timepoint_id, character_name, topic?)` — multi-turn interview

### Step 4.4: Usage analytics

- [ ] `mcp_usage_logs` table (tool_name, user_id, credits_spent, latency_ms, status)
- [ ] Log every tool call
- [ ] Admin dashboard or API for usage stats
- [ ] Prometheus metrics at `/metrics` (future)

### Step 4.5: Wallet identity bridge

- [ ] Map Proteus wallet addresses to Timepoint user accounts
- [ ] Allow wallet-based auth as an alternative to Apple Sign-In

---

## Implementation Priority

```
Week 1:  Phase 1 (Steps 1.1 → 1.8)
         Deliverable: 7 read-only tools live at mcp.timepointai.com

Week 2:  Phase 2 (Steps 2.1 → 2.6)
         Deliverable: generation + credits working

Week 3:  Phase 2 (Steps 2.7 → 2.9)
         Deliverable: billing integration + Stripe checkout

Week 4:  Phase 3 (Steps 3.1 → 3.2)
         Deliverable: simulations working

Future:  Phase 3 OAuth + Phase 4
```

---

## Verification Checklist

After each phase, verify:

- [ ] `/health` returns `{"status": "ok"}` with correct tool count
- [ ] Anonymous search works with no API key (rate limited)
- [ ] Authenticated search works with API key
- [ ] Tool descriptions appear in Claude Desktop's tool list
- [ ] Rate limiting kicks in at the correct threshold
- [ ] (Phase 2+) Credit deduction works correctly
- [ ] (Phase 2+) Insufficient credits returns actionable error with upgrade URL
- [ ] (Phase 2+) Tier resolution matches billing subscription state
- [ ] (Phase 2+) Stripe checkout creates valid session
