"""Tests for mcp-server-linemetrics."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mcp_server_linemetrics.server import (
    _get_access_token,
    _parse_datetime,
    check_device_status,
    get_device_sensors,
    get_timeseries,
    list_devices,
)


def _mock_response(json_data):
    """Create a mock httpx.Response with sync .json() and .raise_for_status()."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


class TestParseDateTime:
    def test_full_iso_format(self):
        dt = _parse_datetime("2024-01-15T10:30:00Z")
        assert dt == datetime(2024, 1, 15, 10, 30, 0)

    def test_iso_without_z(self):
        dt = _parse_datetime("2024-01-15T10:30:00")
        assert dt == datetime(2024, 1, 15, 10, 30, 0)

    def test_date_only(self):
        dt = _parse_datetime("2024-01-15")
        assert dt == datetime(2024, 1, 15)

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Cannot parse datetime"):
            _parse_datetime("not-a-date")


class TestGetAccessToken:
    @pytest.mark.anyio
    async def test_missing_env_vars_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            async with httpx.AsyncClient() as client:
                with pytest.raises(Exception, match="environment variables are required"):
                    await _get_access_token(client)

    @pytest.mark.anyio
    async def test_successful_token(self):
        mock_resp = _mock_response({"access_token": "test_token_123"})

        with (
            patch.dict(
                "os.environ",
                {"LINEMETRICS_CLIENT_ID": "id", "LINEMETRICS_CLIENT_SECRET": "secret"},
            ),
            patch.object(httpx.AsyncClient, "post", return_value=mock_resp),
        ):
            async with httpx.AsyncClient() as client:
                token = await _get_access_token(client)
                assert token == "test_token_123"


class TestListDevices:
    @pytest.mark.anyio
    async def test_returns_devices(self):
        token_resp = _mock_response({"access_token": "tok"})
        devices_resp = _mock_response({
            "d1": {"lmId": "12345", "title": "Device 1", "type": "TypeA"},
            "d2": {"lmId": "67890", "title": "Device 2", "type": "TypeB"},
        })

        with (
            patch.dict(
                "os.environ",
                {"LINEMETRICS_CLIENT_ID": "id", "LINEMETRICS_CLIENT_SECRET": "secret"},
            ),
            patch.object(httpx.AsyncClient, "post", return_value=token_resp),
            patch.object(httpx.AsyncClient, "get", return_value=devices_resp),
        ):
            devices = await list_devices()
            assert len(devices) == 2
            ids = {d["id"] for d in devices}
            assert "12345" in ids
            assert "67890" in ids

    @pytest.mark.anyio
    async def test_empty_account(self):
        token_resp = _mock_response({"access_token": "tok"})
        devices_resp = _mock_response({})

        with (
            patch.dict(
                "os.environ",
                {"LINEMETRICS_CLIENT_ID": "id", "LINEMETRICS_CLIENT_SECRET": "secret"},
            ),
            patch.object(httpx.AsyncClient, "post", return_value=token_resp),
            patch.object(httpx.AsyncClient, "get", return_value=devices_resp),
        ):
            devices = await list_devices()
            assert devices == []


class TestGetDeviceSensors:
    @pytest.mark.anyio
    async def test_returns_sensors(self):
        token_resp = _mock_response({"access_token": "tok"})
        device_resp = _mock_response({
            "data": {"attributes": {"title": "Device 1", "type": "TypeA"}},
            "included": [
                {"id": "m1", "attributes": {"title": "Temperature"}},
                {"id": "m2", "attributes": {"title": "Humidity"}},
            ],
        })

        with (
            patch.dict(
                "os.environ",
                {"LINEMETRICS_CLIENT_ID": "id", "LINEMETRICS_CLIENT_SECRET": "secret"},
            ),
            patch.object(httpx.AsyncClient, "post", return_value=token_resp),
            patch.object(httpx.AsyncClient, "get", return_value=device_resp),
        ):
            result = await get_device_sensors("12345")
            assert result["device_id"] == "12345"
            assert len(result["sensors"]) == 2
            assert result["sensors"][0]["title"] == "Temperature"
            assert result["sensors"][0]["measurement_id"] == "m1"


class TestGetTimeseries:
    @pytest.mark.anyio
    async def test_returns_datapoints(self):
        token_resp = _mock_response({"access_token": "tok"})
        ts_resp = _mock_response([
            {"ts": 1704067200000, "val": 25.5},
            {"ts": 1704067800000, "val": 26.0},
        ])

        with (
            patch.dict(
                "os.environ",
                {"LINEMETRICS_CLIENT_ID": "id", "LINEMETRICS_CLIENT_SECRET": "secret"},
            ),
            patch.object(httpx.AsyncClient, "post", return_value=token_resp),
            patch.object(httpx.AsyncClient, "get", return_value=ts_resp),
        ):
            data = await get_timeseries("m123", "2024-01-01", "2024-01-02")
            assert len(data) == 2
            assert data[0]["value"] == 25.5
            assert "timestamp" in data[0]

    @pytest.mark.anyio
    async def test_empty_timeseries(self):
        token_resp = _mock_response({"access_token": "tok"})
        ts_resp = _mock_response([])

        with (
            patch.dict(
                "os.environ",
                {"LINEMETRICS_CLIENT_ID": "id", "LINEMETRICS_CLIENT_SECRET": "secret"},
            ),
            patch.object(httpx.AsyncClient, "post", return_value=token_resp),
            patch.object(httpx.AsyncClient, "get", return_value=ts_resp),
        ):
            data = await get_timeseries("m123", "2024-01-01")
            assert data == []


class TestCheckDeviceStatus:
    @pytest.mark.anyio
    async def test_online_device(self):
        token_resp = _mock_response({"access_token": "tok"})
        device_resp = _mock_response({
            "data": {"attributes": {"title": "Device 1"}},
            "included": [{"id": "m1", "attributes": {"title": "Temp"}}],
        })
        ts_resp = _mock_response([{"ts": 1704067200000, "val": 25.5}])

        async def mock_get(url, **kwargs):
            if "device-inputs" in url:
                return ts_resp
            return device_resp

        with (
            patch.dict(
                "os.environ",
                {"LINEMETRICS_CLIENT_ID": "id", "LINEMETRICS_CLIENT_SECRET": "secret"},
            ),
            patch.object(httpx.AsyncClient, "post", return_value=token_resp),
            patch.object(httpx.AsyncClient, "get", side_effect=mock_get),
        ):
            result = await check_device_status("12345")
            assert result["status"] == "Online"
            assert result["sensor_count"] == 1

    @pytest.mark.anyio
    async def test_offline_device(self):
        token_resp = _mock_response({"access_token": "tok"})
        device_resp = _mock_response({
            "data": {"attributes": {"title": "Device 1"}},
            "included": [{"id": "m1", "attributes": {"title": "Temp"}}],
        })
        ts_resp = _mock_response([])

        async def mock_get(url, **kwargs):
            if "device-inputs" in url:
                return ts_resp
            return device_resp

        with (
            patch.dict(
                "os.environ",
                {"LINEMETRICS_CLIENT_ID": "id", "LINEMETRICS_CLIENT_SECRET": "secret"},
            ),
            patch.object(httpx.AsyncClient, "post", return_value=token_resp),
            patch.object(httpx.AsyncClient, "get", side_effect=mock_get),
        ):
            result = await check_device_status("12345")
            assert result["status"] == "Offline"
