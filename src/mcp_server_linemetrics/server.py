"""MCP server for interacting with the LineMetrics REST API.

Provides tools to list devices, retrieve sensor metadata,
fetch timeseries data, and check device online status.

Environment variables:
    LINEMETRICS_CLIENT_ID: OAuth client ID for the LineMetrics account.
    LINEMETRICS_CLIENT_SECRET: OAuth client secret for the LineMetrics account.
"""

import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

BASE_URL = "https://restapi.linemetrics.com"
REQUEST_TIMEOUT = 30.0
TIMESERIES_TIMEOUT = 120.0

mcp = FastMCP(
    "LineMetrics",
    instructions="Access devices, sensors, and timeseries data from the LineMetrics IoT platform",
)


class AuthError(Exception):
    """Raised when authentication with LineMetrics fails."""


async def _get_access_token(client: httpx.AsyncClient) -> str:
    """Retrieve an OAuth access token using client credentials."""
    client_id = os.environ.get("LINEMETRICS_CLIENT_ID")
    client_secret = os.environ.get("LINEMETRICS_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise AuthError(
            "LINEMETRICS_CLIENT_ID and LINEMETRICS_CLIENT_SECRET environment variables are required"
        )

    response = await client.post(
        f"{BASE_URL}/oauth/access_token",
        json={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/json"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise AuthError("No access_token in response")
    return token


async def _authed_get(
    client: httpx.AsyncClient,
    token: str,
    path: str,
    params: dict | None = None,
    timeout: float = REQUEST_TIMEOUT,
) -> dict | list:
    """Make an authenticated GET request to the LineMetrics API."""
    response = await client.get(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
async def list_devices() -> list[dict]:
    """List all devices in the LineMetrics account.

    Returns a list of devices, each with id, title, and type.
    """
    async with httpx.AsyncClient() as client:
        token = await _get_access_token(client)
        data = await _authed_get(client, token, "/v2/devices/all")

        devices = []
        if data:
            for value in data.values():
                devices.append({
                    "id": value.get("lmId"),
                    "title": value.get("title"),
                    "type": value.get("type"),
                })
        return devices


@mcp.tool()
async def get_device_sensors(device_id: str) -> dict:
    """Get detailed information about a device and its sensors.

    Args:
        device_id: The LineMetrics device ID (lmId).

    Returns a dict with device metadata and a list of sensors,
    each containing a title and measurement_id.
    """
    async with httpx.AsyncClient() as client:
        token = await _get_access_token(client)
        data = await _authed_get(client, token, "/v2/devices", params={"lmId": device_id})

        sensors = []
        for item in data.get("included", []):
            sensors.append({
                "title": item["attributes"]["title"],
                "measurement_id": item["id"],
            })

        device_attrs = data.get("data", {}).get("attributes", {})
        return {
            "device_id": device_id,
            "title": device_attrs.get("title", ""),
            "type": device_attrs.get("type", ""),
            "sensors": sensors,
        }


@mcp.tool()
async def get_timeseries(
    measurement_id: str,
    start: str,
    end: str | None = None,
    granularity_minutes: int = 15,
    timezone: str = "Europe/Vienna",
) -> list[dict]:
    """Retrieve timeseries data for a specific sensor measurement.

    Args:
        measurement_id: The sensor measurement ID (from get_device_sensors).
        start: Start time in ISO 8601 format (e.g. '2024-01-01' or '2024-01-01T00:00:00Z').
        end: End time in ISO 8601 format. Defaults to now.
        granularity_minutes: Data aggregation interval in minutes. Defaults to 15.
        timezone: Timezone for the data. Defaults to 'Europe/Vienna'.

    Returns a list of data points, each with 'timestamp' (ISO 8601) and 'value'.
    """
    start_dt = _parse_datetime(start)
    end_dt = _parse_datetime(end) if end else datetime.now()

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    async with httpx.AsyncClient() as client:
        token = await _get_access_token(client)
        data = await _authed_get(
            client,
            token,
            f"/v2/device-inputs/{measurement_id}/data",
            params={
                "time_from": start_ms,
                "time_to": end_ms,
                "granularity": f"PT{granularity_minutes}M",
                "time_zone": timezone,
            },
            timeout=TIMESERIES_TIMEOUT,
        )

        return [
            {
                "timestamp": datetime.fromtimestamp(point["ts"] / 1000, tz=UTC).isoformat(),
                "value": point["val"],
            }
            for point in data
        ]


@mcp.tool()
async def check_device_status(device_id: str) -> dict:
    """Check if a device is online by looking for data in the last 7 days.

    Args:
        device_id: The LineMetrics device ID (lmId).

    Returns the device status with title, sensor count, and online/offline status.
    """
    async with httpx.AsyncClient() as client:
        token = await _get_access_token(client)
        data = await _authed_get(client, token, "/v2/devices", params={"lmId": device_id})

        sensors = []
        for item in data.get("included", []):
            sensors.append({
                "title": item["attributes"]["title"],
                "measurement_id": item["id"],
            })

        status = "Offline"
        if sensors:
            one_week_ago = datetime.now() - timedelta(days=7)
            start_ms = int(one_week_ago.timestamp() * 1000)
            end_ms = int(datetime.now().timestamp() * 1000)

            first_measurement_id = sensors[0]["measurement_id"]
            try:
                ts_data = await _authed_get(
                    client,
                    token,
                    f"/v2/device-inputs/{first_measurement_id}/data",
                    params={
                        "time_from": start_ms,
                        "time_to": end_ms,
                        "granularity": "PT15M",
                        "time_zone": "Europe/Vienna",
                    },
                    timeout=TIMESERIES_TIMEOUT,
                )
                if ts_data:
                    status = "Online"
            except httpx.HTTPStatusError:
                status = "Error"

        device_attrs = data.get("data", {}).get("attributes", {})
        return {
            "device_id": device_id,
            "title": device_attrs.get("title", ""),
            "sensor_count": len(sensors),
            "status": status,
        }


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime string."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: '{value}'. Use ISO 8601 format.")


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
