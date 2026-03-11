"""Clockchain tools — read-only access to the temporal causal graph.

All tools in this module are free (no credits required) and available
to anonymous users (rate-limited) and all authenticated tiers.
"""

import logging
from typing import Annotated

from pydantic import Field

logger = logging.getLogger("mcp.tools.clockchain")


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
        - 'causes' — this event directly caused the neighbor
        - 'contemporaneous' — happened at the same time
        - 'same_location' — happened in the same place
        - 'thematic' — shares themes or figures

        Use this to trace causal chains, find related events, and understand how
        historical moments connect to each other.
        """
        result = await clockchain_client.neighbors(path.strip("/"))
        if isinstance(result, dict) and "error" in result:
            return {"error": "Moment not found.", "suggestion": f"Verify the path with get_moment first. Path tried: {path}"}
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
        return await clockchain_client.stats()
