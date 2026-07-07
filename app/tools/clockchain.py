"""Clockchain tools — read-only access to the temporal causal graph.

All tools in this module are free (no credits required) and available
to anonymous users (rate-limited) and all authenticated tiers.
"""

import logging
from typing import Annotated

from pydantic import Field

from app.config import get_settings

logger = logging.getLogger("mcp.tools.clockchain")

VALID_EDGE_TYPES = {
    "causes", "caused_by", "influences", "contemporaneous", "same_era",
    "same_location", "same_conflict", "same_figure", "thematic",
    "precedes", "follows", "challenges",
}

VALID_DIRECTIONS = {"past", "future", "both"}


def _invalid_edge_types(edge_types: str | None) -> list[str]:
    """Return any CSV tokens that are not valid Clockchain edge types."""
    if not edge_types:
        return []
    return [t.strip() for t in edge_types.split(",") if t.strip() and t.strip() not in VALID_EDGE_TYPES]


def register_clockchain_tools(mcp, clockchain_client):
    """Register all Clockchain read tools on the MCP server."""

    @mcp.tool()
    async def search_moments(
        query: Annotated[str, Field(description="Natural language search query, e.g. 'fall of Rome' or 'ancient Egypt'")],
        year_from: Annotated[int | None, Field(description="Filter: earliest year (use negative for BCE, e.g. -500)")] = None,
        year_to: Annotated[int | None, Field(description="Filter: latest year")] = None,
        limit: Annotated[int, Field(description="Max results to return (1-100)", ge=1, le=100)] = 20,
    ) -> dict:
        """Search the Timepoint temporal causal graph for historical events and moments.

        Use this tool when you need to find historical events by topic, person, place,
        or time period. Returns matching moments with names, dates, locations, and
        relevance scores. Results include image URLs when available.

        Examples:
        - search_moments("Julius Caesar") — find events involving Caesar
        - search_moments("ancient rome", year_from=-500, year_to=100)
        - search_moments("industrial revolution", limit=5)
        """
        results = await clockchain_client.search(query, limit=limit)
        if isinstance(results, dict) and "error" in results:
            return {"error": results["detail"], "suggestion": "Try broader search terms or a different query."}
        items = []
        for r in results:
            item = {
                "path": r.get("path", ""),
                "name": r.get("name", ""),
                "one_liner": r.get("one_liner", ""),
                "year": r.get("year", 0),
                "month": r.get("month", 0),
                "day": r.get("day", 0),
                "image_url": r.get("image_url") or None,
                "score": r.get("score", 0.0),
            }
            # Apply year filters client-side if the API doesn't support them
            if year_from is not None and item["year"] and item["year"] < year_from:
                continue
            if year_to is not None and item["year"] and item["year"] > year_to:
                continue
            items.append(item)
        return {
            "items": items[:limit],
            "total": len(items),
            "has_more": len(results) >= limit,
            "query": query,
        }

    @mcp.tool()
    async def get_moment(
        path: Annotated[str, Field(description="Canonical path to the moment, e.g. '/44/march/15/1200/italy/lazio/rome/assassination-of-julius-caesar'")],
        format: Annotated[str, Field(description="Response format: 'default' for full detail or 'tdf' for Timepoint Data Format")] = "default",
    ) -> dict:
        """Get full detail for a specific historical moment by its canonical path.

        Use this after search_moments to get complete information about a moment,
        including its narrative, figures involved, tags, image, and causal connections
        to other events in the graph.

        The path comes from search results or browse_graph output.
        """
        result = await clockchain_client.get_moment(path, format=format)
        if isinstance(result, dict) and "error" in result:
            return {"error": "Moment not found.", "suggestion": f"Use search_moments or browse_graph to find valid paths. Path tried: {path}"}
        return result

    @mcp.tool()
    async def browse_graph(
        path: Annotated[str, Field(description="Path prefix to browse. Use '/' for root, then drill into years, months, etc.")] = "/",
    ) -> dict:
        """Browse the temporal graph hierarchy like a filesystem of history.

        The graph is organized: year → month → day → time → country → region → city → event.

        Start with browse_graph('/') to see available years, then drill down:
        - browse_graph('/') → list of years with event counts
        - browse_graph('/1776') → months in 1776
        - browse_graph('/1776/july') → days in July 1776
        - browse_graph('/1776/july/4') → events on July 4, 1776

        Use this for structured exploration when you want to see what's available
        in a specific time period, rather than searching by keyword.
        """
        result = await clockchain_client.browse(path.strip("/"))
        if isinstance(result, dict) and "error" in result:
            return {"error": "Path not found.", "suggestion": "Start with browse_graph('/') to see available top-level paths."}
        return result

    @mcp.tool()
    async def get_connections(
        path: Annotated[str, Field(description="Canonical path to the moment")],
    ) -> dict:
        """Get causal and thematic connections for a historical moment.

        Returns neighboring events in the temporal graph with their relationship types:
        - 'causes' / 'caused_by' — direct causal relationships
        - 'influences' — indirect causal influence
        - 'contemporaneous' — happened at the same time
        - 'same_location' — happened in the same place
        - 'same_era' — happened in the same historical era
        - 'same_conflict' — part of the same conflict or war
        - 'same_figure' — involves the same historical figure
        - 'thematic' — shares themes
        - 'precedes' / 'follows' — temporal ordering

        Edges include a 'description' field with an explanation of why two events
        are related. Use this to trace causal chains, find related events, and
        understand how historical moments connect to each other.
        """
        result = await clockchain_client.neighbors(path.strip("/"))
        if isinstance(result, dict) and "error" in result:
            return {"error": "Moment not found.", "suggestion": f"Verify the path with get_moment first. Path tried: {path}"}
        return result

    @mcp.tool()
    async def traverse_moments(
        path: Annotated[str, Field(description="Canonical path of the anchor moment, e.g. '/1914/june/28/1030/bosnia/sarajevo/assassination-of-franz-ferdinand'. Get paths from search_moments or browse_graph.")],
        direction: Annotated[str, Field(description="Temporal direction to walk: 'past' (what led to this), 'future' (what this led to), or 'both'")] = "both",
        depth: Annotated[int, Field(description="How many hops to walk from the anchor (1-4). Depth 1 equals get_connections; 2-3 reveals chains; 4 maps a whole neighborhood.", ge=1, le=4)] = 2,
        edge_types: Annotated[str | None, Field(description="Comma-separated edge types to follow. Default: causes,caused_by,precedes,follows,influences (the causal core). Add contemporaneous, same_era, same_location, same_conflict, same_figure, thematic, or challenges to widen the walk.")] = None,
        limit: Annotated[int, Field(description="Max nodes to return (1-200). The response sets truncated=true if this clipped the walk.", ge=1, le=200)] = 50,
    ) -> dict:
        """Walk the causal graph N hops from a moment to map its causes and consequences.

        Where get_connections shows only direct neighbors (1 hop), this tool follows
        chains of connections outward — e.g. anchor -> what it caused -> what THAT
        caused — returning a subgraph of nodes (each tagged with its 'hop' distance
        from the anchor) and the edges linking them.

        Use this when the user asks about ripple effects, root causes, chains of
        events, or "how did X lead to Y" style questions:
        - traverse_moments(path, direction="past", depth=3) — trace root causes
        - traverse_moments(path, direction="future", depth=3) — trace downstream consequences
        - traverse_moments(path, edge_types="causes,caused_by") — strict causality only

        Returns {anchor, direction, depth, nodes[], edges[], node_count, edge_count,
        truncated}. Nodes carry name/year/era/location and hop (0 = the anchor).
        For a single moment's direct links, prefer get_connections; to connect two
        specific moments, prefer find_path.
        """
        if direction not in VALID_DIRECTIONS:
            return {
                "error": f"Invalid direction '{direction}'.",
                "suggestion": "Use 'past', 'future', or 'both'.",
            }
        bad_types = _invalid_edge_types(edge_types)
        if bad_types:
            return {
                "error": f"Invalid edge_types: {', '.join(bad_types)}.",
                "suggestion": f"Valid types: {', '.join(sorted(VALID_EDGE_TYPES))}.",
            }
        try:
            result = await clockchain_client.traverse(
                path, direction=direction, depth=depth, edge_types=edge_types, limit=limit
            )
        except Exception as e:
            logger.warning("traverse_moments failed for %s: %s", path, e)
            return {
                "error": "Clockchain traverse request failed.",
                "suggestion": "Try again, or reduce depth/limit if the request was large.",
            }
        if isinstance(result, dict) and "error" in result:
            return {
                "error": "Anchor moment not found.",
                "suggestion": f"Use search_moments or browse_graph to find a valid path. Path tried: {path}",
            }
        return result

    @mcp.tool()
    async def find_path(
        from_path: Annotated[str, Field(description="Canonical path of the starting moment")],
        to_path: Annotated[str, Field(description="Canonical path of the destination moment")],
        max_hops: Annotated[int, Field(description="Max connections to cross before giving up (1-10). More hops finds longer chains but weaker relationships.", ge=1, le=10)] = 6,
    ) -> dict:
        """Find the shortest chain of historical connections linking two moments.

        Use this when the user asks how two events are related, e.g. "how does the
        assassination of Franz Ferdinand connect to the Treaty of Versailles?".
        The graph is searched in both directions across causal and thematic edges,
        and the first shortest path is returned as an ordered walk: nodes[] from
        the start moment to the destination (hop = position along the path) plus
        the edges[] crossed, each with a type and a description explaining why the
        two moments are linked.

        Returns {found, from, to, hops, nodes[], edges[]}. found=false means the
        moments exist but no chain connects them within max_hops — try raising
        max_hops before concluding they are unrelated. An error is returned only
        when one of the two paths does not exist in the graph.

        To explore outward from a single moment instead, use traverse_moments.
        """
        try:
            result = await clockchain_client.path(from_path, to_path, max_hops=max_hops)
        except Exception as e:
            logger.warning("find_path failed for %s -> %s: %s", from_path, to_path, e)
            return {
                "error": "Clockchain path request failed.",
                "suggestion": "Try again, or lower max_hops if the request was large.",
            }
        if isinstance(result, dict) and "error" in result:
            return {
                "error": "One or both moments were not found.",
                "suggestion": f"Verify both paths with get_moment or search_moments. Tried: {from_path} -> {to_path}",
            }
        return result

    @mcp.tool()
    async def explore_graph(
        path: Annotated[str, Field(description="Canonical path of the root moment, e.g. '/1914/june/28/1030/bosnia/sarajevo/assassination-of-franz-ferdinand'. Get paths from search_moments or browse_graph.")],
        depth: Annotated[int, Field(description="Hop radius around the root (1-3). 1 = direct neighborhood; 3 = wide local map.", ge=1, le=3)] = 1,
        cap: Annotated[int, Field(description="Max nodes to return (1-200). The strongest-weighted connections are kept first; meta.truncated=true means the cap clipped the neighborhood.", ge=1, le=200)] = 100,
    ) -> dict:
        """Agent-native view of the live Explore instrument: a bounded induced subgraph around a moment.

        Returns the same neighborhood the interactive Explore page renders —
        nodes (each tagged with its 'hop' distance from the root) plus ALL edges
        among them (the full induced subgraph, not just a spanning tree), ranked
        by edge weight and causal priority when the cap forces truncation.

        The response includes a web_url deep link to share with the user so they
        can open the same subgraph in the live Explore instrument in their
        browser and keep navigating visually.

        Use this when the user wants an overview map around one moment; for
        directional cause/effect walks use traverse_moments, and to connect two
        specific moments use find_path.

        Returns {nodes[], edges[], meta:{root, depth, cap, truncated, counts},
        web_url}.
        """
        # Clamp defensively (mirrors the client clamps) so the web_url deep
        # link always carries the depth actually requested upstream.
        depth = min(max(depth, 1), 3)
        cap = min(max(cap, 1), 200)
        try:
            result = await clockchain_client.subgraph(path, depth=depth, cap=cap)
        except Exception as e:
            logger.warning("explore_graph failed for %s: %s", path, e)
            return {
                "error": "Clockchain subgraph request failed.",
                "suggestion": "Try again, or reduce depth/cap if the request was large.",
            }
        if isinstance(result, dict) and "error" in result:
            return {
                "error": "Moment not found.",
                "suggestion": f"Use search_moments or browse_graph to find a valid path. Path tried: {path}",
            }
        web_app_url = get_settings().WEB_APP_URL.rstrip("/")
        result["web_url"] = f"{web_app_url}/explore/{path.strip('/')}?depth={depth}"
        return result

    @mcp.tool()
    async def today_in_history() -> dict:
        """Get historical events that happened on today's date (month and day).

        Returns moments from the temporal graph that share today's month and day,
        spanning different years and eras. Good for daily discovery and conversation
        starters.
        """
        return await clockchain_client.today()

    @mcp.tool()
    async def random_moment() -> dict:
        """Get a random historical moment from the temporal graph.

        Good for serendipitous discovery, creative writing prompts, or when the user
        wants to explore something unexpected. Each call returns a different moment.
        """
        return await clockchain_client.random()

    @mcp.tool()
    async def graph_stats() -> dict:
        """Get statistics about the Timepoint temporal knowledge graph.

        Returns total nodes (historical moments), total edges (connections),
        date range covered, distribution by source type and layer, and the
        number of nodes with AI-generated images.

        Use this to understand the scope and coverage of the graph.
        """
        data = await clockchain_client.stats()
        if isinstance(data, dict) and "total_nodes" in data and "total_moments" not in data:
            # Alias total_nodes -> total_moments: in the Timepoint domain,
            # graph nodes are historical moments. Clockchain uses "total_nodes"
            # internally; expose "total_moments" as the canonical public field.
            data = {**data, "total_moments": data["total_nodes"]}
        return data
