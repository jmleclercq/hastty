"""Regression test: HA setups with no "default" Lovelace dashboard.

Reported in https://github.com/jmleclercq/hastty/issues/1 — some real HA
installs have every dashboard replaced by a custom one, so `lovelace/config`
with no url_path answers `config_not_found` instead of a config. hastty used
to crash on startup in that case; it should now fall back to whatever
dashboards do exist, even with include_extra_dashboards left at its default
(False).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hastty.app import HasttyApp
from hastty.config import AppConfig
from tests import mock_ha_server
from tests.mock_ha_server import run_server


async def main() -> None:
    mock_ha_server.SIMULATE_NO_DEFAULT_DASHBOARD = True
    mock_ha_server.EXTRA_DASHBOARDS = [{"url_path": "custom", "title": "Custom"}]
    mock_ha_server.EXTRA_DASHBOARD_CONFIGS = {
        "custom": {
            "views": [
                {"title": "Kitchen", "path": "kitchen", "cards": [{"type": "entities", "entities": ["light.living_room"]}]},
            ]
        }
    }

    runner = await run_server(8769)
    try:
        cfg = AppConfig(base_url="http://127.0.0.1:8769", token="test-token")
        assert cfg.include_extra_dashboards is False, "this test only means something with the opt-in left off"

        app = HasttyApp(cfg)
        async with app.run_test() as pilot:
            await pilot.pause()
            await asyncio.sleep(0.3)

            assert len(app.screen_stack) == 1, "app crashed on startup with no default dashboard"
            assert app.client is not None, "HA client did not connect"
            assert len(app.views) == 1, f"expected the fallback 'Custom' dashboard's view, got {app.views}"
            assert app.views[0].title == "Custom / Kitchen"
            print("OK: no default dashboard (config_not_found) doesn't crash, falls back to listed dashboards")

        print("\nALL TESTS PASSED")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
