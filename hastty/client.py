"""Async client for the Home Assistant API (WebSocket + REST).

Uses the WebSocket API to:
  - authenticate with a Long-Lived Access Token
  - fetch the state of every entity
  - fetch the Lovelace dashboard configuration (views/cards)
  - subscribe to state changes (live updates)
  - call services (turn on/off, toggle, scenes, scripts...)
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import aiohttp

log = logging.getLogger(__name__)

StateChangeCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class HAAuthError(RuntimeError):
    """Raised when WebSocket authentication fails (invalid/expired token)."""


class HAConnectionError(RuntimeError):
    """Raised when the connection to Home Assistant fails (unreachable URL, etc.)."""


def _ws_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.startswith("https://"):
        return base_url.replace("https://", "wss://", 1) + "/api/websocket"
    if base_url.startswith("http://"):
        return base_url.replace("http://", "ws://", 1) + "/api/websocket"
    raise ValueError(f"Invalid Home Assistant URL: {base_url!r} (must start with http:// or https://)")


@dataclass
class HAClient:
    base_url: str
    token: str
    verify_ssl: bool = True

    _session: Optional[aiohttp.ClientSession] = field(default=None, init=False, repr=False)
    _ws: Optional[aiohttp.ClientWebSocketResponse] = field(default=None, init=False, repr=False)
    _id_counter: itertools.count = field(default_factory=lambda: itertools.count(1), init=False, repr=False)
    _pending: dict[int, asyncio.Future] = field(default_factory=dict, init=False, repr=False)
    _listen_task: Optional[asyncio.Task] = field(default=None, init=False, repr=False)
    _state_listeners: list[StateChangeCallback] = field(default_factory=list, init=False, repr=False)
    _connected_evt: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    async def connect(self) -> None:
        """Open the WebSocket connection and authenticate."""
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        self._session = aiohttp.ClientSession(connector=connector)
        try:
            self._ws = await self._session.ws_connect(_ws_url(self.base_url), heartbeat=30)
        except aiohttp.ClientError as exc:
            await self._session.close()
            raise HAConnectionError(f"Could not connect to {self.base_url}: {exc}") from exc

        hello = await self._ws.receive_json()
        if hello.get("type") != "auth_required":
            raise HAConnectionError(f"Unexpected response from Home Assistant: {hello}")

        await self._ws.send_json({"type": "auth", "access_token": self.token})
        auth_result = await self._ws.receive_json()
        if auth_result.get("type") != "auth_ok":
            raise HAAuthError(
                "Authentication rejected by Home Assistant: check your Long-Lived Access Token "
                f"(response: {auth_result})"
            )

        self._listen_task = asyncio.create_task(self._listen_loop())
        self._connected_evt.set()
        log.info("Connected to Home Assistant (%s)", self.base_url)

    async def close(self) -> None:
        if self._listen_task:
            self._listen_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------ #
    # Incoming message loop (responses + pushed events)
    # ------------------------------------------------------------------ #
    async def _listen_loop(self) -> None:
        assert self._ws is not None
        try:
            async for msg in self._ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                msg_id = data.get("id")
                msg_type = data.get("type")

                if msg_type == "result" and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(data)
                elif msg_type == "event":
                    await self._dispatch_event(data)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            log.exception("Error in the WebSocket listen loop")

    async def _dispatch_event(self, data: dict[str, Any]) -> None:
        event = data.get("event", {})
        if event.get("event_type") != "state_changed":
            return
        new_state = event.get("data", {}).get("new_state")
        if not new_state:
            return
        for cb in list(self._state_listeners):
            result = cb(new_state)
            if asyncio.iscoroutine(result):
                await result

    def on_state_change(self, callback: StateChangeCallback) -> None:
        self._state_listeners.append(callback)

    # ------------------------------------------------------------------ #
    # Generic WebSocket command dispatch
    # ------------------------------------------------------------------ #
    async def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self._ws is not None, "connect() must be called before any request"
        msg_id = next(self._id_counter)
        payload = {**payload, "id": msg_id}
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        await self._ws.send_json(payload)
        result = await asyncio.wait_for(fut, timeout=15)
        if not result.get("success", True):
            raise RuntimeError(f"HA command failed ({payload.get('type')}): {result.get('error')}")
        return result.get("result")

    # ------------------------------------------------------------------ #
    # High-level API
    # ------------------------------------------------------------------ #
    async def subscribe_state_changed(self) -> None:
        await self._send({"type": "subscribe_events", "event_type": "state_changed"})

    async def get_states(self) -> list[dict[str, Any]]:
        return await self._send({"type": "get_states"})

    async def list_lovelace_dashboards(self) -> list[dict[str, Any]]:
        """List additional Lovelace dashboards (besides the default one)."""
        try:
            return await self._send({"type": "lovelace/dashboards/list"})
        except RuntimeError:
            return []

    async def get_lovelace_config(self, url_path: Optional[str] = None) -> dict[str, Any]:
        """Fetch the config (views/cards) of a Lovelace dashboard.

        url_path=None -> default dashboard.
        """
        payload: dict[str, Any] = {"type": "lovelace/config"}
        if url_path:
            payload["url_path"] = url_path
        return await self._send(payload)

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: Optional[str] = None,
        service_data: Optional[dict[str, Any]] = None,
    ) -> Any:
        target = {"entity_id": entity_id} if entity_id else {}
        payload = {
            "type": "call_service",
            "domain": domain,
            "service": service,
            "service_data": service_data or {},
            "target": target,
        }
        return await self._send(payload)
