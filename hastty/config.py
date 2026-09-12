"""Configuration loading: HA connection + custom keyboard shortcuts."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

DEFAULT_CONFIG_PATH = Path(
    os.environ.get("HASTTY_CONFIG", str(Path.home() / ".config" / "hastty" / "config.yaml"))
)


@dataclass
class Shortcut:
    key: str
    description: str
    domain: str
    service: str
    entity_id: Optional[str] = None
    service_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    base_url: str
    token: str
    verify_ssl: bool = True
    refresh_interval: float = 0.0  # 0 = no polling, relies on WS events
    include_extra_dashboards: bool = False
    shortcuts: list[Shortcut] = field(default_factory=list)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path: Optional[Path] = None) -> AppConfig:
    """Load the config from a YAML file, with fallback/override from environment variables.

    Priority for url/token: HA_URL / HA_TOKEN environment variables
    (also loaded from a local .env file if present) > YAML file.
    """
    load_dotenv()  # loads .env from the current directory if present
    config_path = path or DEFAULT_CONFIG_PATH
    raw = _load_yaml(config_path)

    ha_cfg = raw.get("homeassistant", {}) or {}
    base_url = os.environ.get("HA_URL") or ha_cfg.get("url")
    token = os.environ.get("HA_TOKEN") or ha_cfg.get("token")

    if not base_url or not token:
        raise RuntimeError(
            "Incomplete configuration: set HA_URL and HA_TOKEN (environment variables "
            "or a .env file), or fill in 'homeassistant.url'/'homeassistant.token' in "
            f"{config_path}.\n"
            "Generate a Long-Lived Access Token from your Home Assistant profile "
            "(Settings > your profile > Security > Long-lived access tokens)."
        )

    verify_ssl = bool(ha_cfg.get("verify_ssl", True))
    include_extra_dashboards = bool(ha_cfg.get("include_extra_dashboards", False))

    shortcuts = []
    for item in raw.get("keybindings", []) or []:
        target = item.get("target", {}) or {}
        shortcuts.append(
            Shortcut(
                key=str(item["key"]),
                description=item.get("description", item["key"]),
                domain=item["service"].split(".", 1)[0],
                service=item["service"].split(".", 1)[1],
                entity_id=target.get("entity_id"),
                service_data=item.get("service_data", {}) or {},
            )
        )

    return AppConfig(
        base_url=base_url,
        token=token,
        verify_ssl=verify_ssl,
        include_extra_dashboards=include_extra_dashboards,
        shortcuts=shortcuts,
    )


def write_example_config(path: Optional[Path] = None) -> Path:
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    example = """\
# hastty configuration
#
# The URL and token can (and preferably should) also be provided via
# HA_URL / HA_TOKEN environment variables, or a local .env file, to avoid
# storing the token in plain text here.

homeassistant:
  url: "http://homeassistant.local:8123"
  token: ""          # Long-Lived Access Token (HA profile > Security)
  verify_ssl: true
  # If you have more than one Lovelace dashboard and want hastty to mirror
  # all of them (not just your default one), set this to true.
  include_extra_dashboards: false

# Global keyboard shortcuts: available from any view, to trigger a command
# directly (scene, script, automation...) without navigating to the entity
# in the table first.
keybindings:
  - key: "g"
    description: "Good night (scene)"
    service: "scene.turn_on"
    target:
      entity_id: scene.good_night

  - key: "a"
    description: "Turn everything off (script)"
    service: "script.turn_on"
    target:
      entity_id: script.turn_everything_off
"""
    config_path.write_text(example, encoding="utf-8")
    return config_path
