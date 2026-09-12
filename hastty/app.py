"""Textual application: Home Assistant dashboard viewer + keyboard shortcuts."""

from __future__ import annotations

import logging
from typing import Optional

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane

from .client import HAAuthError, HAClient, HAConnectionError
from .config import AppConfig, Shortcut
from .lovelace import ViewDef, default_action_for, views_from_lovelace_config

log = logging.getLogger(__name__)

_DOMAIN_ICONS = {
    "light": "💡",
    "switch": "🔌",
    "sensor": "📈",
    "binary_sensor": "🔔",
    "climate": "🌡️",
    "cover": "🪟",
    "fan": "🌀",
    "lock": "🔒",
    "media_player": "🎵",
    "scene": "🎬",
    "script": "📜",
    "automation": "⚙️",
    "person": "🧑",
    "device_tracker": "📍",
    "vacuum": "🧹",
    "camera": "📷",
    "weather": "⛅",
    "input_boolean": "🔘",
    "button": "🔲",
}


def _icon_for(entity_id: str) -> str:
    return _DOMAIN_ICONS.get(entity_id.split(".", 1)[0], "•")


def _format_state(state: dict) -> str:
    val = state.get("state", "?")
    unit = (state.get("attributes") or {}).get("unit_of_measurement")
    if unit:
        return f"{val} {unit}"
    return val


class HelpScreen(ModalScreen[None]):
    """Modal screen listing every available shortcut."""

    BINDINGS = [Binding("escape,question_mark,q", "dismiss", "Close")]

    def __init__(self, shortcuts: list[Shortcut]) -> None:
        super().__init__()
        self._shortcuts = shortcuts

    def compose(self) -> ComposeResult:
        lines = [
            "[b]Navigation[/b]",
            "  ←/→ or 1-9      switch view",
            "  ↑/↓ or j/k       move the selection",
            "  Enter / Space    activate the selected entity (toggle/scene/script...)",
            "  r                refresh",
            "  ?                this help screen",
            "  q                quit",
            "",
        ]
        if self._shortcuts:
            lines.append("[b]Custom shortcuts (config)[/b]")
            for sc in self._shortcuts:
                lines.append(f"  {sc.key:<3}             {sc.description}")
        else:
            lines.append("[dim]No custom shortcut defined in the config.[/dim]")
        yield Vertical(Static("\n".join(lines), id="help-body"))
        yield Footer()

    def action_dismiss(self) -> None:
        self.dismiss(None)


class HasttyApp(App):
    """Terminal viewer for Home Assistant dashboards, with keyboard shortcuts."""

    CSS = """
    #help-body { padding: 1 2; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "show_help", "Help"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter,space", "activate_selected", "Activate"),
    ]

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config_ = config
        self.client: Optional[HAClient] = None
        self.views: list[ViewDef] = []
        self.states: dict[str, dict] = {}
        # entity_id -> list of (table_id, row_key) for live updates
        self._entity_locations: dict[str, list[tuple[str, str]]] = {}
        self._custom_shortcuts: dict[str, Shortcut] = {s.key: s for s in config.shortcuts}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield TabbedContent(id="tabs")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = "Home Assistant — Dashboard"
        self.sub_title = self.config_.base_url
        await self._connect_and_load()

    async def _connect_and_load(self) -> None:
        self.sub_title = f"{self.config_.base_url} — connecting..."
        try:
            self.client = HAClient(self.config_.base_url, self.config_.token, self.config_.verify_ssl)
            await self.client.connect()
            await self.client.subscribe_state_changed()
            self.client.on_state_change(self._on_state_changed_sync)
        except (HAAuthError, HAConnectionError) as exc:
            self.sub_title = f"Connection error: {exc}"
            log.error("HA connection failed: %s", exc)
            return

        await self._load_dashboard()

    async def _load_dashboard(self) -> None:
        assert self.client is not None
        states_list = await self.client.get_states()
        self.states = {s["entity_id"]: s for s in states_list}

        lovelace_cfg = await self.client.get_lovelace_config()
        self.views = views_from_lovelace_config(lovelace_cfg)

        if self.config_.include_extra_dashboards:
            extra_dashboards = await self.client.list_lovelace_dashboards()
            for dash in extra_dashboards:
                url_path = dash.get("url_path")
                if not url_path:
                    continue
                try:
                    cfg = await self.client.get_lovelace_config(url_path)
                except RuntimeError:
                    continue
                for v in views_from_lovelace_config(cfg):
                    v.title = f"{dash.get('title', url_path)} / {v.title}"
                    self.views.append(v)

        await self._render_views()
        self.sub_title = f"{self.config_.base_url} — {len(self.views)} view(s), {len(self.states)} entities"

    async def _render_views(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        # clear_panes() only schedules removal (returns an AwaitComplete); the
        # old ContentTab widgets aren't actually gone until this is awaited.
        # Without it, re-adding a pane with the same id right after (e.g. on
        # "r" refresh) races the teardown and Textual raises DuplicateIds.
        await tabs.clear_panes()
        self._entity_locations.clear()

        if not self.views:
            tabs.add_pane(TabPane("No view", Static("No Lovelace view found.")))
            return

        for i, view in enumerate(self.views):
            table_id = f"table-{i}"
            table = DataTable(id=table_id, cursor_type="row", zebra_stripes=True)
            table.add_columns("", "Entity", "State")
            for eid in view.entity_ids:
                state = self.states.get(eid)
                friendly = (state.get("attributes", {}).get("friendly_name") if state else None) or eid
                display_state = _format_state(state) if state else "unavailable"
                table.add_row(_icon_for(eid), friendly, display_state, key=eid)
                # DataTable's RowKey has no meaningful __str__ (its default repr
                # includes a memory address), so we must keep the entity_id
                # itself as the lookup key, not str(row_key).
                self._entity_locations.setdefault(eid, []).append((table_id, eid))
            pane = TabPane(view.title or f"View {i + 1}", table, id=f"pane-{i}")
            tabs.add_pane(pane)

    # ------------------------------------------------------------------ #
    # Live updates
    # ------------------------------------------------------------------ #
    def _on_state_changed_sync(self, new_state: dict) -> None:
        # Called from the HA client's asyncio loop; scheduling through
        # call_later is enough since it runs on the same event loop as Textual.
        self.call_later(self._apply_state_update, new_state)

    async def _apply_state_update(self, new_state: dict) -> None:
        eid = new_state["entity_id"]
        self.states[eid] = new_state
        for table_id, row_key in self._entity_locations.get(eid, []):
            try:
                table = self.query_one(f"#{table_id}", DataTable)
            except Exception:  # noqa: BLE001
                continue
            display_state = _format_state(new_state)
            try:
                col_keys = list(table.columns.keys())
                table.update_cell(row_key, col_keys[2], display_state)
            except Exception:  # noqa: BLE001
                log.debug("Could not update the cell for %s", eid)

    # ------------------------------------------------------------------ #
    # General actions
    # ------------------------------------------------------------------ #
    def action_show_help(self) -> None:
        self.push_screen(HelpScreen(self.config_.shortcuts))

    def action_refresh(self) -> None:
        self.run_worker(self._load_dashboard(), exclusive=True)

    def action_activate_selected(self) -> None:
        try:
            tabs = self.query_one("#tabs", TabbedContent)
            active_pane = tabs.get_pane(tabs.active)
            table = active_pane.query_one(DataTable)
        except Exception:  # noqa: BLE001
            return
        if table.row_count == 0 or table.cursor_row is None:
            return
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        except Exception:  # noqa: BLE001
            return
        entity_id = row_key.value if row_key is not None else None
        if not entity_id:
            return
        action = default_action_for(entity_id)
        if not action:
            self.notify(f"No quick action for {entity_id}", severity="warning")
            return
        domain, service = action
        self.run_worker(self._call_service(domain, service, entity_id), exclusive=False)

    async def _call_service(self, domain: str, service: str, entity_id: Optional[str], data: Optional[dict] = None) -> None:
        if not self.client:
            return
        try:
            await self.client.call_service(domain, service, entity_id, data)
            label = entity_id or f"{domain}.{service}"
            self.notify(f"{domain}.{service} → {label}", timeout=2)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"Call to {domain}.{service} failed: {exc}", severity="error", timeout=5)

    async def on_key(self, event: events.Key) -> None:
        # Custom shortcuts defined in the config (active globally).
        shortcut = self._custom_shortcuts.get(event.key)
        if shortcut:
            event.stop()
            await self._call_service(shortcut.domain, shortcut.service, shortcut.entity_id, shortcut.service_data)
            return

        # Quick view switch via number keys 1-9.
        if event.key.isdigit():
            idx = int(event.key) - 1
            if 0 <= idx < len(self.views):
                tabs = self.query_one("#tabs", TabbedContent)
                tabs.active = f"pane-{idx}"
                event.stop()

    async def on_unmount(self) -> None:
        if self.client:
            await self.client.close()
