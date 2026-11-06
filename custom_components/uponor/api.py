"""Async client for the Uponor Smatrix Pulse R-208 JNAP API."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

ACTION_GET = "http://phyn.com/jnap/uponorsky/GetAttributes"
ACTION_SET = "http://phyn.com/jnap/uponorsky/SetAttributes"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class UponorApiError(Exception):
    """Raised when the Uponor controller cannot be reached or rejects a request."""


class UponorJnapClient:
    """Minimal async replacement for the unmaintained UponorJnap library."""

    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self._session = session
        self._url = f"http://{host}/JNAP/"

    async def _post(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._session.post(
                self._url,
                headers={"x-jnap-action": action},
                data=json.dumps(payload),
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                # The controller does not always send a JSON content type.
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise UponorApiError(f"Error communicating with {self._url}: {err}") from err

    async def get_data(self) -> dict[str, str]:
        """Return all controller variables as a name -> value mapping."""
        data = await self._post(ACTION_GET, {})
        try:
            return {
                var["waspVarName"]: var["waspVarValue"]
                for var in data["output"]["vars"]
            }
        except (KeyError, TypeError) as err:
            raise UponorApiError(f"Unexpected response from controller: {data}") from err

    async def send_data(self, data: dict[str, Any]) -> None:
        """Write one or more controller variables."""
        payload = {
            "vars": [
                {"waspVarName": k, "waspVarValue": str(v)} for k, v in data.items()
            ]
        }
        result = await self._post(ACTION_SET, payload)
        if "result" in result and result["result"] != "OK":
            raise UponorApiError(f"Controller rejected update: {result}")
