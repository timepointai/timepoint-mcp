"""Regression tests for the Starlette + FastMCP HTTP routing layout.

Task el-cg0zq / spec el-1w5ry: the deployed standalone MCP server returned 404
for ``POST /mcp/`` while ``GET /health`` reported 200, so the dashboard health
check missed the regression. Root cause: ``mcp.http_app(path="/mcp")`` was
mounted by Starlette at ``/mcp``, and Starlette strips the mount prefix before
delegating to the sub-app — so the only URL that matched was ``/mcp/mcp``.

These tests lock the URL layout in place so the bug cannot regress silently:

  * POST ``/mcp/`` reaches the FastMCP Streamable HTTP handler (status 200).
  * The double-prefix path ``/mcp/mcp`` is NOT a valid handshake URL.
  * Plain HTTP endpoints (``/``, ``/health``) keep working alongside the mount.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


INITIALIZE_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "regression-test", "version": "1.0"},
    },
}
INITIALIZE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


@pytest.fixture
def http_app():
    """Fresh app per test — the FastMCP lifespan owns a task group that cannot
    be reused across TestClient sessions."""
    # Import inside the fixture so module-level side effects (including the
    # ``http_app = create_http_app()`` at the bottom of ``app.server``) are
    # paid once but each test still drives lifespan via TestClient.
    from app.server import create_http_app
    return create_http_app()


def test_post_mcp_trailing_slash_reaches_handler(http_app):
    """POST /mcp/ must reach the FastMCP handler — not 404.

    A 404 here means the FastMCP sub-app's ``path=`` argument and the parent
    Starlette ``mount(...)`` prefix have stacked into ``/mcp/mcp``. The MCP
    Streamable HTTP client does not auto-redirect, and ``POST /mcp/`` is the
    canonical handshake URL — a 404 takes the whole public MCP surface down.
    """
    with TestClient(http_app) as client:
        resp = client.post("/mcp/", json=INITIALIZE_BODY, headers=INITIALIZE_HEADERS)
    assert resp.status_code != 404, (
        "POST /mcp/ returned 404 — the FastMCP mount is mis-stacked. "
        "Check that mcp.http_app(path=...) is built with path='/' when the "
        "parent Starlette app mounts it at '/mcp'."
    )
    # 200 is the happy path; 202/406 etc. would also indicate the route
    # reached the MCP handler. The contract we lock here is "not 404".
    assert resp.status_code < 500, f"unexpected server error {resp.status_code}: {resp.text[:200]}"


def test_post_mcp_double_prefix_does_not_serve_handler(http_app):
    """/mcp/mcp must NOT be the working handshake URL.

    This is the exact symptom the regression caused on production. Locking
    it down stops a future "mount at correct prefix but set sub-app path
    back to /mcp" change from reintroducing the bug while masking it with
    a still-working /mcp/mcp endpoint.
    """
    with TestClient(http_app) as client:
        resp = client.post("/mcp/mcp", json=INITIALIZE_BODY, headers=INITIALIZE_HEADERS)
    # /mcp/mcp should be a 404 (no route), NOT a 200 handshake response.
    assert resp.status_code == 404, (
        f"POST /mcp/mcp returned {resp.status_code} — the MCP handler is "
        "double-mounted. The canonical URL is /mcp/."
    )


def test_health_and_root_still_work(http_app):
    """The MCP mount must not shadow the plain HTTP endpoints."""
    with TestClient(http_app) as client:
        health = client.get("/health")
        root = client.get("/", headers={"accept": "application/json"})
    assert health.status_code == 200
    assert health.json().get("status") in {"ok", "degraded"}
    assert root.status_code == 200
    body = root.json()
    assert body.get("service") == "Timepoint MCP Server"
