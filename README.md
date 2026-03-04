# mcp-server-linemetrics

An [MCP](https://modelcontextprotocol.io) server for the [LineMetrics](https://www.linemetrics.com) REST API. Gives LLMs access to IoT device metadata, sensor information, and timeseries data from the LineMetrics platform.

## Tools

| Tool | Description |
|------|-------------|
| `list_devices` | List all devices in the account with their IDs, titles, and types |
| `get_device_sensors` | Get detailed device info and its sensors (title + measurement ID) |
| `get_timeseries` | Fetch timeseries data for a sensor measurement with configurable time range and granularity |
| `check_device_status` | Check whether a device is online (has reported data in the last 7 days) |

## Setup

### Prerequisites

You need LineMetrics API credentials (OAuth client ID and secret). These are obtained from your LineMetrics account.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LINEMETRICS_CLIENT_ID` | Yes | Your LineMetrics OAuth client ID |
| `LINEMETRICS_CLIENT_SECRET` | Yes | Your LineMetrics OAuth client secret |

### Install

```bash
# Using uv (recommended)
uv pip install mcp-server-linemetrics

# Using pip
pip install mcp-server-linemetrics
```

### Usage with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "linemetrics": {
      "command": "uvx",
      "args": ["mcp-server-linemetrics"],
      "env": {
        "LINEMETRICS_CLIENT_ID": "your_client_id",
        "LINEMETRICS_CLIENT_SECRET": "your_client_secret"
      }
    }
  }
}
```

### Usage with Claude Code

```bash
claude mcp add linemetrics -- uvx mcp-server-linemetrics \
  -e LINEMETRICS_CLIENT_ID=your_client_id \
  -e LINEMETRICS_CLIENT_SECRET=your_client_secret
```

### Run Directly

```bash
export LINEMETRICS_CLIENT_ID=your_client_id
export LINEMETRICS_CLIENT_SECRET=your_client_secret
mcp-server-linemetrics
```

## Development

```bash
git clone https://github.com/bbruhn91/mcp-server-linemetrics.git
cd mcp-server-linemetrics
uv sync --dev
uv run pytest
```

## License

MIT
