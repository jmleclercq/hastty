"""Flattens the Lovelace configuration (views -> cards -> entities) into displayable rows.

Lovelace dashboards have a heterogeneous structure (entities card, glance,
vertical-stack, grid, light, thermostat, tile, area, etc.). We don't try to
reproduce everything visually: we extract the list of entity_ids referenced
by each view, in the order they appear, which is enough for a terminal
"viewer" that stays faithful to the dashboard's organization.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Card types that contain other, nested cards.
_STACK_CARD_TYPES = {"vertical-stack", "horizontal-stack", "grid"}


@dataclass
class ViewDef:
    title: str
    path: str
    entity_ids: list[str] = field(default_factory=list)


def _extract_from_card(card: dict, out: list[str]) -> None:
    if not isinstance(card, dict):
        return

    card_type = card.get("type", "")

    if card_type in _STACK_CARD_TYPES:
        for sub in card.get("cards", []):
            _extract_from_card(sub, out)
        return

    # "entities"/"glance"/"badges" card: heterogeneous entity list
    # (raw str "light.living_room" or dict {"entity": "light.living_room", ...}).
    entities = card.get("entities")
    if isinstance(entities, list):
        for e in entities:
            if isinstance(e, str):
                out.append(e)
            elif isinstance(e, dict) and "entity" in e:
                out.append(e["entity"])

    # Single-entity card (light, thermostat, media-control, tile, gauge...).
    single = card.get("entity")
    if isinstance(single, str):
        out.append(single)

    # "area" card: no directly usable entity_id, skipped for now.


def views_from_lovelace_config(config: dict) -> list[ViewDef]:
    """Convert the raw `lovelace/config` response into a list of ViewDef."""
    views_out: list[ViewDef] = []
    for idx, view in enumerate(config.get("views", [])):
        title = view.get("title") or view.get("path") or f"View {idx + 1}"
        path = view.get("path") or str(idx)
        entity_ids: list[str] = []
        for card in view.get("cards", []):
            _extract_from_card(card, entity_ids)
        # de-duplicate while preserving order
        seen = set()
        deduped = []
        for eid in entity_ids:
            if eid not in seen:
                seen.add(eid)
                deduped.append(eid)
        views_out.append(ViewDef(title=title, path=path, entity_ids=deduped))
    return views_out


# Default service to call when "activating" an entity (Enter/Space key),
# based on its domain. Missing domain => no generic action available.
DEFAULT_TOGGLE_SERVICE: dict[str, tuple[str, str]] = {
    "light": ("light", "toggle"),
    "switch": ("switch", "toggle"),
    "fan": ("fan", "toggle"),
    "input_boolean": ("input_boolean", "toggle"),
    "cover": ("cover", "toggle"),
    "lock": ("lock", "toggle"),
    "siren": ("siren", "toggle"),
    "media_player": ("media_player", "media_play_pause"),
    "scene": ("scene", "turn_on"),
    "script": ("script", "turn_on"),
    "automation": ("automation", "trigger"),
    "button": ("button", "press"),
    "input_button": ("input_button", "press"),
    "vacuum": ("vacuum", "toggle"),
    "climate": ("climate", "toggle"),
}


def default_action_for(entity_id: str) -> tuple[str, str] | None:
    domain = entity_id.split(".", 1)[0]
    return DEFAULT_TOGGLE_SERVICE.get(domain)
