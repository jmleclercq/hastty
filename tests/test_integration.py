"""End-to-end integration test against the mock server (no real HA instance)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hastty.app import HasttyApp
from hastty.config import AppConfig, Shortcut
from tests.mock_ha_server import CALLED_SERVICES, run_server


async def main() -> None:
    runner = await run_server(8765)
    try:
        cfg = AppConfig(
            base_url="http://127.0.0.1:8765",
            token="test-token",
            shortcuts=[
                Shortcut(key="g", description="Good night", domain="scene", service="turn_on", entity_id="scene.good_night")
            ],
        )
        app = HasttyApp(cfg)
        async with app.run_test() as pilot:
            await pilot.pause()
            await asyncio.sleep(0.3)

            assert app.client is not None, "HA client did not connect"
            assert len(app.views) == 2, f"expected 2 views, got {len(app.views)}"
            assert app.views[0].title == "Living Room"
            assert app.views[0].entity_ids == ["light.living_room", "switch.tv", "sensor.living_room_temp"]
            assert app.views[1].entity_ids == ["scene.good_night"]
            print("OK: Lovelace views mirrored correctly")

            # Select the 1st row (light.living_room, off) and activate it (Enter)
            await pilot.press("enter")
            await asyncio.sleep(0.3)
            assert any(s["domain"] == "light" and s["service"] == "toggle" for s in CALLED_SERVICES), CALLED_SERVICES
            assert app.states["light.living_room"]["state"] == "on", app.states["light.living_room"]
            print("OK: activated the selected entity (toggle light.living_room) + live state update")

            # Global custom shortcut "g" -> scene.turn_on on scene.good_night
            await pilot.press("g")
            await asyncio.sleep(0.3)
            assert any(s["domain"] == "scene" and s["service"] == "turn_on" for s in CALLED_SERVICES), CALLED_SERVICES
            print("OK: custom shortcut ('g' key -> scene.turn_on)")

            # Switch view via the "2" key
            tabs = app.query_one("#tabs")
            await pilot.press("2")
            await asyncio.sleep(0.2)
            assert tabs.active == "pane-1", tabs.active
            print("OK: view switch via number key")

            # Help
            await pilot.press("question_mark")
            await pilot.pause()
            assert len(app.screen_stack) == 2
            print("OK: help screen")

        print("\nALL INTEGRATION TESTS PASSED")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
