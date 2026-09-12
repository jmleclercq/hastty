"""A small WebSocket server that mimics the subset of the HA API hastty uses.

Only used for local integration tests (no real HA instance required).
"""

from __future__ import annotations

from aiohttp import web

STATES = [
    {"entity_id": "light.living_room", "state": "off", "attributes": {"friendly_name": "Living Room Light"}},
    {"entity_id": "switch.tv", "state": "on", "attributes": {"friendly_name": "TV"}},
    {"entity_id": "sensor.living_room_temp", "state": "21.5", "attributes": {"friendly_name": "Living Room Temp.", "unit_of_measurement": "°C"}},
    {"entity_id": "scene.good_night", "state": "scening", "attributes": {"friendly_name": "Good Night"}},
    {"entity_id": "light.garden", "state": "off", "attributes": {"friendly_name": "Garden Light"}},
]

LOVELACE_CONFIG = {
    "views": [
        {
            "title": "Living Room",
            "path": "living-room",
            "cards": [
                {"type": "entities", "entities": ["light.living_room", {"entity": "switch.tv"}]},
                {"type": "vertical-stack", "cards": [{"type": "sensor", "entity": "sensor.living_room_temp"}]},
            ],
        },
        {
            "title": "Scenes",
            "path": "scenes",
            "cards": [{"type": "glance", "entities": ["scene.good_night"]}],
        },
        {
            # Modern "sections" dashboard layout (default editor since HA
            # 2024.9): entities live under sections, not a top-level "cards" list.
            "title": "Garden",
            "path": "garden",
            "type": "sections",
            "sections": [
                {"type": "grid", "cards": [{"type": "tile", "entity": "light.garden"}]},
            ],
        },
        {
            "title": "Empty",
            "path": "empty",
            "cards": [],
        },
    ]
}

CALLED_SERVICES: list[dict] = []

# Some real HA setups have no "default" (no url_path) dashboard at all —
# every dashboard was replaced by a custom one. Toggle this to simulate that:
# lovelace/config with no url_path then answers config_not_found, like real
# HA does, instead of falling back to LOVELACE_CONFIG.
SIMULATE_NO_DEFAULT_DASHBOARD = False
EXTRA_DASHBOARDS: list[dict] = []
EXTRA_DASHBOARD_CONFIGS: dict[str, dict] = {}


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    await ws.send_json({"type": "auth_required", "ha_version": "test"})
    auth_msg = await ws.receive_json()
    if auth_msg.get("access_token") != "test-token":
        await ws.send_json({"type": "auth_invalid", "message": "invalid token"})
        await ws.close()
        return ws
    await ws.send_json({"type": "auth_ok", "ha_version": "test"})

    async for msg in ws:
        if msg.type != web.WSMsgType.TEXT:
            continue
        data = msg.json()
        msg_id = data["id"]
        mtype = data["type"]

        if mtype == "get_states":
            await ws.send_json({"id": msg_id, "type": "result", "success": True, "result": STATES})
        elif mtype == "lovelace/config":
            url_path = data.get("url_path")
            if url_path is None and SIMULATE_NO_DEFAULT_DASHBOARD:
                await ws.send_json(
                    {
                        "id": msg_id,
                        "type": "result",
                        "success": False,
                        "error": {"code": "config_not_found", "message": "No config found."},
                    }
                )
            elif url_path and url_path in EXTRA_DASHBOARD_CONFIGS:
                await ws.send_json({"id": msg_id, "type": "result", "success": True, "result": EXTRA_DASHBOARD_CONFIGS[url_path]})
            else:
                await ws.send_json({"id": msg_id, "type": "result", "success": True, "result": LOVELACE_CONFIG})
        elif mtype == "lovelace/dashboards/list":
            await ws.send_json({"id": msg_id, "type": "result", "success": True, "result": EXTRA_DASHBOARDS})
        elif mtype == "subscribe_events":
            await ws.send_json({"id": msg_id, "type": "result", "success": True, "result": None})
        elif mtype == "call_service":
            CALLED_SERVICES.append(data)
            await ws.send_json({"id": msg_id, "type": "result", "success": True, "result": {}})
            # simulate the real state change that would follow the service call
            target = data.get("target", {})
            eid = target.get("entity_id")
            if eid:
                for s in STATES:
                    if s["entity_id"] == eid:
                        s["state"] = "on" if s["state"] == "off" else "off"
                        await ws.send_json(
                            {
                                "id": msg_id + 1000,
                                "type": "event",
                                "event": {"event_type": "state_changed", "data": {"entity_id": eid, "new_state": s}},
                            }
                        )
        else:
            await ws.send_json({"id": msg_id, "type": "result", "success": True, "result": None})

    return ws


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/websocket", ws_handler)
    return app


async def run_server(port: int) -> web.AppRunner:
    runner = web.AppRunner(make_app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    return runner
