"""Capture SVG screenshots of the app against the mock server, for the README."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hastty.app import HasttyApp
from hastty.config import AppConfig, Shortcut
from tests.mock_ha_server import run_server

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "screenshots"


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = await run_server(8766)
    try:
        cfg = AppConfig(
            base_url="http://127.0.0.1:8766",
            token="test-token",
            shortcuts=[
                Shortcut(key="g", description="Good night (scene)", domain="scene", service="turn_on", entity_id="scene.good_night"),
                Shortcut(key="a", description="Turn everything off", domain="script", service="turn_on", entity_id="script.turn_everything_off"),
            ],
        )
        app = HasttyApp(cfg)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.3)

            # "Living Room" view, cursor on the 2nd row
            await pilot.press("down")
            await pilot.pause()
            svg = app.export_screenshot(title="hastty — Living Room view")
            (OUT_DIR / "01-view-living-room.svg").write_text(svg, encoding="utf-8")

            # Activate the selected entity to show the live state + notification
            await pilot.press("enter")
            await asyncio.sleep(0.3)
            svg = app.export_screenshot(title="hastty — activating an entity")
            (OUT_DIR / "02-activate-entity.svg").write_text(svg, encoding="utf-8")

            # "Scenes" view
            await pilot.press("2")
            await pilot.pause()
            svg = app.export_screenshot(title="hastty — Scenes view")
            (OUT_DIR / "03-view-scenes.svg").write_text(svg, encoding="utf-8")

            # Help screen
            await pilot.press("question_mark")
            await pilot.pause()
            svg = app.export_screenshot(title="hastty — help / shortcuts")
            (OUT_DIR / "04-help.svg").write_text(svg, encoding="utf-8")

        print("Screenshots written to", OUT_DIR)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
