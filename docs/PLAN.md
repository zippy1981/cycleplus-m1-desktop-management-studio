# Delivery plan

Tracking issue: #1. Agent rules: [`AGENTS.md`](../AGENTS.md).

## Decisions made during planning (2026-11-11)

| Topic | Decision | Consequence |
|---|---|---|
| M1 transport | **Unknown, so verify both BLE and USB first** (Phase 0) | The transport layer is pluggable. If USB mass storage exposes FIT files, USB import ships first as the low-risk path. |
| Strava credentials | **Bring-your-own Strava API app** | Each user registers a Strava app and enters its client ID and secret, which are stored in the OS keyring. Nothing secret ships in the binary, there's no backend, and each user stays within Strava's 1-athlete limit for unreviewed apps. #8 and #10 need a guided setup flow. |
| Windows | **Linux first.** Windows runs in CI from day one and gets hardware validation at #11/#12 on the maintainer's Windows machine. | Hardware-dependent "done" checks on Windows are deferred to the end, not dropped. |
| License | **GPL-3.0-or-later** | Compatible with PySide6 (LGPL) and Bleak (MIT). |
| GUI / runtime | PySide6, Python ≥ 3.13, uv | Recorded formally in ADR-0001 (#2). |

## What was verified on the dev machine (user zero)

- Ubuntu 26.04.1 LTS, kernel 7.0, X11/XFCE session.
- BlueZ 5.85 active. Intel 7265 adapter (BT 4.2, supports LE) powered and not rfkill-blocked.
- BLE scanning works as a non-root user. The M1 advertises as `M1_XXXX` once powered on.
- **Phase 0 step 2 done:** read-only GATT enumeration succeeded without pairing. Hardware rev 04, firmware V1.4.1, Nordic nRF chip. Data goes over **Nordic UART Service** plus an extra characteristic `6e400004`, using a private protocol. The device also exposes **Buttonless DFU**, which is now denylisted. Details: `docs/hardware/m1-protocol.md`.
- Python 3.14.4 and uv 0.13.7 present.
- gnome-keyring provides `org.freedesktop.secrets`, so `keyring` will work.
- No Windows machine has been checked yet.

## Open risks and things to verify

1. **The M1 transfer protocol is proprietary and runs over NUS.** This is the biggest risk. Reverse-engineering it needs the HCI snoop capture from Phase 0 step 3, so USB (step 1) is now the cheaper path to check first.
1a. **Firmware drift.** The protocol may change between firmware versions. Record the firmware revision with every download, and refuse unknown major firmware versions until they're verified.
2. **The M1 may advertise only in a sync mode**, or may require bonding. That affects the UX in #4/#10.
3. **Strava API limits and terms.** Check current rate limits and the API Agreement before #8. Strava's upload endpoint is async (`POST /uploads` → poll `GET /uploads/{id}`). Use `external_id` and the "duplicate of activity N" error for reconciliation. The minimum scope is probably `activity:write` alone, but verify whether reading back the upload status needs more.
4. **Strava OAuth for desktop apps.** Use a loopback redirect (`http://localhost:<port>/callback`) with the `state` parameter checked. Access tokens expire after about 6 hours, and refresh tokens rotate, so persist the new refresh token atomically.
5. **Qt on Wayland/XFCE/Windows.** The GUI smoke test runs in CI under `xvfb` on Linux and natively on `windows-latest`.

## Phases

The issue dependency chain is strictly linear. These phases loosen it where work can safely run in parallel.

### Phase 0: Hardware spike (new; do before or alongside #2)

Goal: learn how the M1 actually moves rides, without any writes to the device.

1. **USB:** plug in the M1 and record what appears in `dmesg`, `lsusb`, and `lsblk`. If it's mass storage, list the FIT files and copy one out by hand, then check it parses.
2. **BLE (read-only):** wake the M1 and scan with Bleak. Record the advertised name and service UUIDs. Connect, enumerate GATT, and read only the Device Information Service.
3. **Protocol capture:** enable Android's Bluetooth HCI snoop log, sync a ride with the official CYCPLUS app, then pull the btsnoop log and analyze it in Wireshark. Record the opcodes in `docs/hardware/m1-protocol.md`. The raw capture stays out of the repo.
4. **Output:** a filled-in `docs/hardware/m1-protocol.md` and a recommendation on whether USB, BLE, or both should ship in v1.

**Needs the maintainer:** the device, a USB-C cable, and an Android phone with the CYCPLUS app.

### Phase 1: Foundations (#2, #3)

- **#2: ADRs.** 0001 app architecture and GUI, 0002 provider contract, 0003 device access and destructive-operation guards, 0004 OAuth (BYO app) and credential storage, 0005 FIT archive and retention, 0006 background runtime. Use Phase 0 findings in ADR-0003.
- **#3: Scaffold.**
  - Layout: `src/cycplus_m1_studio/{core,transport,device,providers,sync,gui,cli}`, plus `tests/`.
  - `pyproject.toml` with uv and `uv.lock`, ruff, mypy, and pytest (hardware tests carry the `hardware` marker and are skipped by default). import-linter enforces the boundaries in `AGENTS.md`.
  - CLI: `m1studio --help`, `m1studio diag` (shows platform, Python, BLE adapter, keyring backend, and paths).
  - The GUI shell opens an empty main window.
  - GitHub Actions matrix: ubuntu-latest and windows-latest × Python 3.13 and 3.14, running lint, types, unit tests, and a GUI smoke test.

### Phase 2: Device and archive (#4, #5, #6)

- **#4:** `transport/ble.py` (Bleak) and, if Phase 0 says USB works, `transport/usb.py`. `device/m1.py` sends only allowlisted operations. `m1studio scan` and `m1studio diag gatt`.
- **#5:** Download with resume or a safe restart, validate with the FIT SDK (CRC and header), then write atomically to `archive/<sha256[:2]>/<sha256>.fit`. Detect duplicates by hash. Test fixtures include truncated and malformed files.
- **#6:** SQLite catalog with migrations. Tables: `devices`, `activities` (hash, path, metadata), `provider_sync` (activity × provider: state, remote_id, attempts, last_error, upload_ref). State machine: `discovered → downloading → archived`, and for each provider `pending → uploading → processing → synced | failed | skipped`.

### Phase 3: Providers (#7, #8, #9)

#7 can start once #6's schema is drafted, since it only needs the `provider_sync` shape.

- **#7:** A `Provider` protocol defining capabilities, auth lifecycle, `upload()`, `poll()`, `reconcile()`, and error classification (transient, permanent, or auth). Plugins register through entry points. Includes an in-repo `test` provider (writes to a local directory) used by #9 and #12.
- **#8:** Strava with BYO app credentials, a loopback OAuth flow, keyring storage, token refresh and revocation, upload plus poll, and `external_id` set from the SHA-256.
- **#9:** A durable queue built on `provider_sync`. Bounded exponential backoff with jitter. Before any retry, reconcile ambiguous timeouts using the stored upload ref. Each provider gets its own worker, so one failing provider never blocks another.

### Phase 4: UI and packaging (#10, #11)

#10 can start after #3, using fake services, and gets wired to the real ones as Phases 2–3 land.

- **#10:** Pages for Devices, Activities, Providers (including the Strava BYO setup wizard), Sync queue, Logs, and Settings. Destructive actions sit behind a typed confirmation.
- **#11:** PyInstaller or Briefcase (decided in an ADR). Linux gets AppImage or Flatpak plus an XDG autostart entry or a systemd `--user` unit. Windows gets an MSIX or Inno Setup installer plus a per-user logon Task Scheduler entry. Release builds are signed with checksums. The update check goes to GitHub Releases only.

### Phase 5: Acceptance (#12)

- Hardware checks on Linux and Windows, plus fault injection: kill the process mid-download, drop BLE mid-transfer, and cut the network mid-upload.
- Docs: install guide, Strava BYO setup, privacy and scopes, destructive operations, troubleshooting.

## Proposed issue updates (not applied yet)

- Add a **Phase 0 hardware spike** issue that blocks #4 and informs #2.
- In #4/#5, change "BLE download" to "device transport (BLE and/or USB, per spike)".
- In #8, add the BYO Strava app setup flow and say that no client secret ships in the binary.
- Loosen the dependencies so that #7 depends on #6's schema draft and #10 depends on #3 (using fakes).
