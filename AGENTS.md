# Agent directions

Read this file in full before working in this repo. It applies to every coding agent (Claude Code, Codex, Copilot, etc.) and to humans. The full delivery plan is in [`docs/PLAN.md`](docs/PLAN.md); the tracking issue is #1.

## What this project is

A local-first desktop app (GUI + CLI) for CYCPLUS M1 bike computer owners. It downloads rides from the device, archives the original FIT files unchanged, and can sync them to optional providers. Strava is the first provider, but the app must work fully with every provider disabled.

## Hard safety rules — never break these

1. **Never send a write, command, or "control point" byte to the M1 unless that opcode is listed in `docs/hardware/m1-protocol.md` with its observed meaning.** Discovery and GATT enumeration are read-only. If an opcode is unknown, stop and ask.
2. **No destructive device operations without explicit user confirmation.** That covers delete, format, reset, and firmware. The app never installs firmware.
3. **Never modify, re-encode, or "fix" an archived FIT file.** The archive stores original bytes, content-addressed by SHA-256. Derived data goes in SQLite.
4. **Never commit secrets or personal ride data.** That covers OAuth tokens, Strava client secrets, real FIT files from the maintainer's rides, GPS traces, device serials, and Bluetooth MAC addresses. Test fixtures must be synthetic, or anonymized with GPS stripped/shifted, and labeled as such in `tests/fixtures/README.md`.
5. **Credentials live only in the OS credential store** (via `keyring`). They never go in config files, SQLite, logs, or exception messages. Redact tokens in every log path.
6. **No telemetry, analytics, or crash reporting that phones home.** The only network calls are to provider APIs the user has enabled and the documented update endpoint.
7. **Never require root or an administrator.** The app runs as the logged-in user.

## Hardware access (Linux dev machine)

- BlueZ is active and BLE scanning works without root.
- Before running any test that touches real hardware, confirm the M1 is powered on, and tell the user which test you are about to run.
- Hardware tests carry the `@pytest.mark.hardware` marker and are **skipped by default**. Run them only with `pytest -m hardware --run-hardware`.
- If the M1 doesn't appear in a scan, don't keep retrying. Report it to the user and ask them to wake the device or put it in pairing/sync mode.

## Stack (until an ADR in `docs/adr/` says otherwise)

| Concern | Choice |
|---|---|
| Language | Python ≥ 3.13 (dev machine runs 3.14; CI tests 3.13 and 3.14) |
| Env / deps | `uv` with a committed `uv.lock` |
| GUI | PySide6 (Qt 6, LGPL — dynamically linked) |
| CLI | Typer |
| BLE | Bleak (BlueZ on Linux, WinRT on Windows) |
| FIT parsing | `garmin-fit-sdk` (official) — read-only; never re-encode |
| Storage | stdlib `sqlite3` with numbered migrations; WAL mode |
| HTTP | `httpx` |
| Credentials | `keyring` (Secret Service on Linux, Credential Manager on Windows) |
| Paths | `platformdirs` |
| Quality | `ruff` (lint+format), `mypy --strict` on `src/`, `pytest` |

## Architecture boundaries

```
transport (ble, usb)  →  device protocol (m1)  →  activity core (archive, catalog, state)
                                                         ↑
                                     sync orchestrator → provider API ← providers (strava, test, …)
GUI / CLI  → talk only to application services, never to transport or providers directly
```

- `core/` must not import from `providers/`, `transport/`, `gui/`, or `cli/`. CI enforces this with import-linter.
- Providers receive an immutable activity view (bytes + metadata). They never touch SQLite directly. Each provider's state and remote IDs are stored under that provider's own namespace.
- Providers are discovered through the `cycplus_m1_studio.providers` entry-point group. Adding a provider must not require changes to `core/`.

## Workflow

- One issue per PR. Branch name: `<issue#>-short-slug`. Reference the issue in the PR body (`Closes #N` only when every acceptance criterion is met).
- Before you push: `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest`.
- Behavior changes need tests. Protocol code needs tests against recorded, anonymized captures.
- Record each architecture decision as an ADR in `docs/adr/NNNN-title.md`, using the template there. When an ADR changes the stack table above, update the table in the same PR.
- Don't add a dependency without a one-line reason in the PR body.
- Commit and push only when the user asks you to. Never force-push `main`.

## Naming

The brand is **CYCPLUS** (the repo name spells it "cycleplus"). The Python package is `cycplus_m1_studio`, the CLI command is `m1studio`, and the display name is "CYCPLUS M1 Studio".
