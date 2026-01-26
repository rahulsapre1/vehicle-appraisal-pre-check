"""MCP Server for Vehicle Appraisal Pre-Check System

This server implements the Model Context Protocol (MCP) to expose
appraisal system capabilities to AI assistants like Claude Desktop.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    # Fallback for development - create minimal MCP server structure
    print("Warning: mcp package not installed. Install with: pip install mcp", file=sys.stderr)
    # Create minimal server structure for testing
    class Server:
        def __init__(self, name: str):
            self.name = name
    class stdio_server:
        async def __aenter__(self):
            return (None, None)
        async def __aexit__(self, *args):
            pass
    class Tool:
        pass
    class TextContent:
        pass

# Import tools - handle both local and package imports
try:
    from tools.appraisal_tools import (
        get_appraisal_status,
        check_evidence_completeness,
        get_risk_flags,
        get_decision_readiness,
        get_ledger_events,
    )
except ImportError:
    # Fallback for different import paths
    import sys
    from pathlib import Path
    current_file = Path(__file__).resolve()
    tools_dir = current_file.parent / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from appraisal_tools import (
        get_appraisal_status,
        check_evidence_completeness,
        get_risk_flags,
        get_decision_readiness,
        get_ledger_events,
    )


# Create MCP server instance
app = Server("vehicle-appraisal")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools for the appraisal system."""
    return [
        Tool(
            name="get_appraisal_status",
            description=(
                "Get the current status, readiness score, and decision for an appraisal. "
                "Use this to check if an appraisal is ready, needs more evidence, or should be escalated. "
                "Accepts either UUID or short_id (4 characters) as appraisal_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "appraisal_id": {
                        "type": "string",
                        "description": "UUID or short_id (4 characters) of the appraisal to check",
                    }
                },
                "required": ["appraisal_id"],
            },
        ),
        Tool(
            name="check_evidence_completeness",
            description=(
                "Check what evidence is missing or incomplete for an appraisal. "
                "Returns missing angles, covered angles, photo count, and completeness status. "
                "Accepts either UUID or short_id (4 characters) as appraisal_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "appraisal_id": {
                        "type": "string",
                        "description": "UUID or short_id (4 characters) of the appraisal to check",
                    }
                },
                "required": ["appraisal_id"],
            },
        ),
        Tool(
            name="get_risk_flags",
            description=(
                "Get all risk flags and consistency issues identified for an appraisal. "
                "Returns flags categorized by severity (high, medium, low) with evidence references. "
                "Accepts either UUID or short_id (4 characters) as appraisal_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "appraisal_id": {
                        "type": "string",
                        "description": "UUID or short_id (4 characters) of the appraisal to check",
                    }
                },
                "required": ["appraisal_id"],
            },
        ),
        Tool(
            name="get_decision_readiness",
            description=(
                "Get the decision readiness assessment including score breakdown and next actions. "
                "Shows why an appraisal is ready, needs evidence, or should be escalated. "
                "Accepts either UUID or short_id (4 characters) as appraisal_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "appraisal_id": {
                        "type": "string",
                        "description": "UUID or short_id (4 characters) of the appraisal to check",
                    }
                },
                "required": ["appraisal_id"],
            },
        ),
        Tool(
            name="get_ledger_events",
            description=(
                "Get the complete audit ledger (event log) for an appraisal. "
                "Returns all pipeline execution events in chronological order for debugging and audit. "
                "Accepts either UUID or short_id (4 characters) as appraisal_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "appraisal_id": {
                        "type": "string",
                        "description": "UUID or short_id (4 characters) of the appraisal to check",
                    }
                },
                "required": ["appraisal_id"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a tool and return the result."""
    appraisal_id = arguments.get("appraisal_id")
    
    if not appraisal_id:
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": "appraisal_id is required"}),
            )
        ]
    
    try:
        if name == "get_appraisal_status":
            result = await get_appraisal_status(appraisal_id)
        elif name == "check_evidence_completeness":
            result = await check_evidence_completeness(appraisal_id)
        elif name == "get_risk_flags":
            result = await get_risk_flags(appraisal_id)
        elif name == "get_decision_readiness":
            result = await get_decision_readiness(appraisal_id)
        elif name == "get_ledger_events":
            result = await get_ledger_events(appraisal_id)
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        return [
            TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str),
            )
        ]
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": f"Tool execution failed: {str(e)}"}),
            )
        ]


async def main():
    """Run the MCP server using stdio transport."""
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
    except Exception as e:
        print(f"Error running MCP server: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
