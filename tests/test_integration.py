"""End-to-end integration test against the mock server (no real HA instance)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textual.widgets import DataTable

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
            assert len(app.views) == 4, f"expected 4 views, got {len(app.views)}"
            assert app.views[0].title == "Living Room"
            assert app.views[0].entity_ids == ["light.living_room", "switch.tv", "sensor.living_room_temp"]
            assert app.views[1].entity_ids == ["scene.good_night"]
            print("OK: Lovelace views mirrored correctly")

            # "Garden" uses the modern "sections" layout (no top-level "cards")
            assert app.views[2].title == "Garden"
            assert app.views[2].entity_ids == ["light.garden"], app.views[2].entity_ids
            print("OK: 'sections' dashboard layout parsed correctly")

            # "Empty" has no cards at all: the table has zero rows
            assert app.views[3].title == "Empty"
            assert app.views[3].entity_ids == []
            print("OK: view with no entities is handled gracefully")

            # Select the 1st row (light.living_room, off) and activate it (Enter)
            await pilot.press("enter")
            await asyncio.sleep(0.3)
            assert any(s["domain"] == "light" and s["service"] == "toggle" for s in CALLED_SERVICES), CALLED_SERVICES
            assert app.states["light.living_room"]["state"] == "on", app.states["light.living_room"]
            # Regression: the internal state dict updating isn't enough, the
            # visible DataTable cell must reflect it too (this is what the
            # user actually sees in the terminal).
            table = app.query_one("#table-0", DataTable)
            state_column_key = list(table.columns.keys())[2]
            cell = table.get_cell("light.living_room", state_column_key)
            assert cell == "on", f"table cell still shows {cell!r}, live update did not reach the UI"
            print("OK: activated the selected entity (toggle light.living_room) + live state update in the table")

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
            await pilot.press("escape")
            await pilot.pause()

            # Regression: pressing Enter on a view with an empty table must not
            # crash the app (it used to raise CellDoesNotExist).
            await pilot.press("4")
            await asyncio.sleep(0.2)
            await pilot.press("enter")
            await asyncio.sleep(0.2)
            assert len(app.screen_stack) == 1, "app crashed to the default error screen"
            print("OK: Enter on an empty view doesn't crash the app")

        print("\nALL INTEGRATION TESTS PASSED")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
