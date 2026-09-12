# Contributing to hastty

Thanks for considering a contribution! This project is small on purpose —
please keep that in mind when proposing changes.

## Setup

```bash
git clone https://github.com/jmleclercq/hastty.git
cd hastty
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Running the tests

There's no real Home Assistant instance required: tests run against a
mock WebSocket server that implements the subset of the HA API hastty uses.

```bash
python tests/test_integration.py
```

If you touch the Lovelace parsing (`hastty/lovelace.py`) or live-update
logic (`hastty/app.py`), add a case to `tests/mock_ha_server.py` /
`tests/test_integration.py` that reproduces it rather than only testing by
hand — the "sections" dashboard layout and the row-key live-update bug were
both regressions that manual testing alone had missed.

To regenerate the README screenshots after a UI change:

```bash
python tests/capture_screenshots.py
```

## Making changes

- Keep pull requests focused: one fix or one feature at a time.
- Match the existing style (no comments beyond what explains a non-obvious
  *why*, no speculative abstractions, no error handling for cases that
  can't happen).
- Update the README if you change user-facing behavior (keybindings,
  config options, CLI flags).
- Run `python -m py_compile hastty/*.py tests/*.py` and the integration
  test before opening a PR.

## Reporting bugs

Open an issue with:
- your Home Assistant version,
- the dashboard type involved if relevant (classic `cards`-based view vs.
  the newer `sections` layout),
- what you expected vs. what happened (a screenshot of a crash traceback,
  if any, helps a lot).

## Reporting security issues

Please don't open a public issue for anything involving your Long-Lived
Access Token or credential handling — open a private security advisory on
GitHub instead.
