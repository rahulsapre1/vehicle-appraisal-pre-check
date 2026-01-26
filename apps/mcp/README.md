# MCP Server for Vehicle Appraisal Pre-Check System

This MCP (Model Context Protocol) server exposes appraisal system capabilities to AI assistants like Claude Desktop, allowing them to query appraisal status, check evidence completeness, retrieve risk flags, and access audit logs.

## Overview

The MCP server provides a standardized interface for AI assistants to interact with the Vehicle Appraisal Pre-Check system. It implements the Model Context Protocol specification and exposes tools that call the existing FastAPI endpoints.

## Architecture

```
AI Assistant (Claude Desktop)
    │
    │ MCP Protocol (stdio)
    │
    ▼
MCP Server (apps/mcp)
    │
    │ HTTP/REST
    │
    ▼
FastAPI API (backend/app)
    │
    ▼
Supabase (Database + Storage)
```

## Features

The MCP server exposes 5 read-only tools:

1. **get_appraisal_status** - Get current status, readiness score, and decision
2. **check_evidence_completeness** - Check what evidence is missing
3. **get_risk_flags** - Get all risk flags and consistency issues
4. **get_decision_readiness** - Get readiness assessment with score breakdown
5. **get_ledger_events** - Get complete audit ledger (event log)

## Installation

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (for containerized deployment)
- Access to the Vehicle Appraisal API (running on `http://api:8000`)

### Local Development

```bash
# Install dependencies
cd apps/mcp
pip install -r requirements.txt

# Set environment variables
export API_BASE_URL=http://localhost:8001

# Run MCP server
python server.py
```

### Docker Deployment

The MCP server is included in `docker-compose.yml` with a profile, so it doesn't run by default:

```bash
# Start all services including MCP server
docker-compose --profile mcp up -d

# View MCP server logs
docker-compose logs -f mcp
```

## Configuration

Environment variables:

- `API_BASE_URL` - Base URL of the FastAPI API (default: `http://api:8000`)
- `API_TIMEOUT_SECONDS` - Timeout for API requests in seconds (default: `60.0`)

## Connecting AI Assistants

### Claude Desktop

1. Edit Claude Desktop configuration file (location varies by OS):
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

2. Add MCP server configuration:

```json
{
  "mcpServers": {
    "vehicle-appraisal": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--network=vehicle-appraisal-app_appraisal-network",
        "-e",
        "API_BASE_URL=http://api:8000",
        "vehicle-appraisal-app-mcp:latest",
        "python",
        "server.py"
      ]
    }
  }
}
```

3. **Restart Claude Desktop**

4. The MCP server will start automatically when Claude needs it

### Other MCP Clients

The server uses stdio transport (standard input/output), which is compatible with any MCP client that supports stdio transport.

## Available Tools

### get_appraisal_status

Get the current status, readiness score, and decision for an appraisal.

**Parameters:**
- `appraisal_id` (string, required): UUID or short_id (4 characters) of the appraisal

**Returns:**
- `appraisal_id`: UUID of the appraisal
- `short_id`: Short ID (4 characters)
- `status`: Pipeline run status
- `readiness_score`: Readiness score (0-100)
- `readiness_status`: Decision status (ready, escalate, needs_more_evidence)
- `decision_reasons`: List of reasons for the decision
- `pipeline_run_id`: ID of the latest pipeline run

### check_evidence_completeness

Check what evidence is missing or incomplete for an appraisal.

**Parameters:**
- `appraisal_id` (string, required): UUID or short_id (4 characters) of the appraisal

**Returns:**
- `is_complete`: Whether evidence is complete
- `photo_count`: Number of photos uploaded
- `missing_angles`: List of missing photo angles
- `covered_angles`: List of covered photo angles
- `missing_evidence`: List of missing evidence items

### get_risk_flags

Get all risk flags and consistency issues identified for an appraisal.

**Parameters:**
- `appraisal_id` (string, required): UUID or short_id (4 characters) of the appraisal

**Returns:**
- `total_flags`: Total number of risk flags
- `high_severity_count`: Number of high severity flags
- `medium_severity_count`: Number of medium severity flags
- `low_severity_count`: Number of low severity flags
- `high_severity_flags`: List of high severity flags
- `medium_severity_flags`: List of medium severity flags
- `low_severity_flags`: List of low severity flags
- `all_flags`: All flags with evidence references
- `assumptions`: List of assumptions made
- `unknowns`: List of unknown factors

### get_decision_readiness

Get the decision readiness assessment including score breakdown and next actions.

**Parameters:**
- `appraisal_id` (string, required): UUID or short_id (4 characters) of the appraisal

**Returns:**
- `readiness_score`: Total readiness score (0-100)
- `readiness_status`: Decision status
- `score_breakdown`: Detailed breakdown of scoring components
- `decision_reasons`: List of reasons for the decision
- `next_action`: Recommended next action

### get_ledger_events

Get the complete audit ledger (event log) for an appraisal.

**Parameters:**
- `appraisal_id` (string, required): UUID or short_id (4 characters) of the appraisal

**Returns:**
- `total_events`: Total number of events
- `events`: List of all ledger events in chronological order
- `node_summary`: Summary of pipeline nodes and their status

## Project Structure

```
apps/mcp/
├── __init__.py
├── server.py              # MCP server implementation
├── requirements.txt       # Dependencies (mcp, httpx)
├── Dockerfile             # Container definition
├── README.md              # This file
├── tools/
│   ├── __init__.py
│   └── appraisal_tools.py # Tool implementations
└── tests/
    ├── __init__.py
    └── test_appraisal_tools.py # Tests (to be added)
```

## Troubleshooting

### MCP Server Won't Start

- Check that API is running: `curl http://api:8000/healthz`
- Verify environment variables are set correctly
- Check Docker logs: `docker-compose logs mcp`

### Tools Return Errors

- Verify API endpoints are accessible from MCP server
- Check API logs for errors
- Ensure appraisal IDs are valid (UUID or 4-character short_id)

### Claude Desktop Can't Connect

- Verify Docker container is running: `docker-compose ps mcp`
- Check MCP server logs for connection attempts
- Verify configuration file syntax is valid JSON
- Ensure Docker network name matches: `vehicle-appraisal-app_appraisal-network`

## Security Notes

- MCP server only exposes read-only operations (no write access)
- All API calls use internal Docker network (not exposed externally)
- MCP server runs with minimal privileges
- No authentication required (assumes trusted Docker network)

## Future Enhancements

- Add authentication/authorization
- Support for write operations (with proper security)
- Caching for frequently accessed appraisals
- Webhook support for real-time updates
- Additional tools for cross-squad use cases

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification/latest)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude Desktop MCP Guide](https://docs.anthropic.com/claude/docs/mcp)
