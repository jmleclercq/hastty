"""Generate assets/demo.gif: a short animated walkthrough of hastty, driven
against the local mock Home Assistant server (tests/mock_ha_server.py).

Not part of the automated test suite — a dev tool to (re)build the README's
demo GIF after a UI change. Needs two extra, non-runtime dependencies:

    pip install cairosvg pillow
"""

import asyncio
import sys
from pathlib import Path

import cairosvg
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hastty.app import HasttyApp
from hastty.config import AppConfig, Shortcut
from tests.mock_ha_server import run_server

OUT_DIR = Path(__file__).resolve().parent.parent / "assets"
FRAME_WIDTH = 1000

# Emoji domain icons aren't in cairosvg's font-matching path (no color-emoji
# fallback), so they rasterize as blank tofu boxes. Swap them for plain glyphs
# that the fallback monospace font actually has, for this GIF only — the real
# app/terminal/README screenshots are unaffected.
ICON_SUBSTITUTIONS = {
    "💡": "*",
    "🔌": "~",
    "📈": "^",
    # "<" and ">" are XML-special and must stay escaped in text content, or
    # cairosvg's XML parser chokes on them (they were raw glyphs before, so
    # substituting with literal "<"/">" broke the SVG's well-formedness).
    "🎬": "&gt;",
    "←": "&lt;",
    "→": "&gt;",
    "↑": "^",
    "↓": "v",
}


def _svg_to_frame(svg_text: str) -> Image.Image:
    for emoji, replacement in ICON_SUBSTITUTIONS.items():
        svg_text = svg_text.replace(emoji, replacement)
    png_bytes = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), output_width=FRAME_WIDTH)
    return Image.open(__import__("io").BytesIO(png_bytes)).convert("RGB")


async def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    runner = await run_server(8767)
    frames: list[tuple[Image.Image, int]] = []

    def capture(title: str, duration_ms: int) -> None:
        svg = app.export_screenshot(title=title)
        frames.append((_svg_to_frame(svg), duration_ms))

    try:
        cfg = AppConfig(
            base_url="http://127.0.0.1:8767",
            token="test-token",
            shortcuts=[
                Shortcut(key="g", description="Good night (scene)", domain="scene", service="turn_on", entity_id="scene.good_night"),
            ],
        )
        app = HasttyApp(cfg)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.3)
            capture("hastty — Living Room", 1400)

            await pilot.press("enter")  # toggle light.living_room off -> on
            await asyncio.sleep(0.3)
            capture("hastty — Enter: toggle the light on", 1500)

            await pilot.press("down")  # move to switch.tv
            await pilot.pause()
            capture("hastty — ↓: move the selection", 900)

            await pilot.press("enter")  # toggle switch.tv on -> off
            await asyncio.sleep(0.3)
            capture("hastty — Enter: toggle the TV off", 1500)

            await pilot.press("2")  # switch to Scenes view
            await pilot.pause()
            capture("hastty — 2: jump to the Scenes view", 1300)

            await pilot.press("g")  # custom global shortcut
            await asyncio.sleep(0.3)
            capture("hastty — g: custom shortcut (scene.turn_on)", 1600)

            await pilot.press("question_mark")  # help screen
            await pilot.pause()
            capture("hastty — ?: help and custom shortcuts", 2200)

            await pilot.press("escape")
            await pilot.pause()
            capture("hastty — back to the dashboard", 1600)

        first, rest = frames[0][0], [f for f, _ in frames[1:]]
        durations = [d for _, d in frames]
        first.save(
            OUT_DIR / "demo.gif",
            save_all=True,
            append_images=rest,
            duration=durations,
            loop=0,
            optimize=True,
        )
        print(f"Wrote {OUT_DIR / 'demo.gif'} ({len(frames)} frames)")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
