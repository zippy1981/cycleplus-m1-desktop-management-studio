# CYCPLUS M1 protocol notes

> **Status: GATT layout verified (2026-11-11, Linux/BlueZ 5.85, read-only). The transfer protocol is still unverified.** Per `AGENTS.md` rule 1, the opcode allowlist stays empty until a capture of the official app's sync is recorded here.

## Device identity

| Field | Value | Source |
|---|---|---|
| Advertised name | `M1_XXXX`, where the suffix looks derived from the MAC address | Advertisement local name |
| Advertised service | `6e400001-…` (Nordic UART) | Advertisement; no manufacturer or service data |
| Model | `CYCPLUS M1` | DIS 0x2A24 |
| Manufacturer | `CDZN Tech Co.,Ltd` | DIS 0x2A29 |
| Hardware rev | `04` | DIS 0x2A27 |
| Firmware / software rev | `V1.4.1` / `1.4.1` | DIS 0x2A26 / 0x2A28 |
| Chipset | Nordic nRF5x (inferred from the DFU and NUS services) | |

**Identifying the device:** match on DIS model `CYCPLUS M1`, not on the advertised name. Filter scans on the advertised NUS UUID and `M1_` name prefix, then confirm with DIS after connecting.

Never record the MAC address or serial number here.

## USB

- [ ] Plug in over USB-C on Linux and record `dmesg`, `lsusb`, and `lsblk` output (redact the serial number).
- [ ] Is it USB mass storage? If so, record the directory layout and FIT filenames.
- [ ] Is it read-only or writable? (Do not write to it to find out. Check the mount flags and the device docs.)

## BLE GATT layout

Captured with Bleak by enumerating services and reading only DIS. Default ATT MTU is 23; the negotiated MTU is not measured yet.

| Service | Characteristic | Properties | Purpose / notes |
|---|---|---|---|
| `180a` Device Information | `2a24 2a25 2a26 2a27 2a28 2a29` | read | Identity (see above). **Never log or commit 2a25, the serial number.** |
| `1800` GAP | `2a00` Device Name | read, **write** | ⛔ Never write; it would rename the device. |
| `1800` GAP | `2a01 2a04 2aa6` | read | Standard |
| `fe59` Nordic Secure DFU | `8ec90003-f315-4f60-9fb8-838830daea50` Buttonless DFU | write, indicate | ⛔ **Never write or subscribe.** A write reboots the device into its bootloader to install firmware. |
| `6e400001-…` Nordic UART (NUS) | `6e400002-…` RX | write-without-response | Host→device commands. Proprietary protocol, unknown. |
| `6e400001-…` NUS | `6e400003-…` TX | notify | Device→host responses / data |
| `6e400001-…` NUS | `6e400004-b5a3-f393-e0a9-e50e24dcca9e` | write-without-response, write, notify | Non-standard extra characteristic. Probably the bulk file-transfer channel; unknown. |
| `180f` Battery | `2a19` | read, notify | Battery %. Safe to read. |
| `1801` GATT | `2a05` Service Changed | indicate | Standard |

### Denylist (enforced in code, not just docs)

- Anything in service `fe59` (DFU)
- `2a00` writes (device name)
- Any write to `6e400002`/`6e400004` whose opcode isn't in the allowlist below

## Observed transfer protocol

Source: an HCI snoop capture of the official CYCPLUS phone app syncing a ride. Keep the raw capture out of the repo; commit only an anonymized summary.

The transport is NUS, so the protocol is a private framed byte protocol. Expect a file-list command, a get-file command with chunking and an offset, and probably a delete command. The delete command must be identified and **listed as destructive** before any other opcode is allowlisted. Do not reconstruct the protocol from guesses or third-party projects for other models (M2/M3).

## Opcode allowlist

| Opcode / write | Characteristic | Meaning | Destructive? | Evidence |
|---|---|---|---|---|
| — | — | — | — | — |

## Connection behavior

- Connect / disconnect / reconnect timing: _TBD_
- Advertises while powered on: **yes** (seen at -34 dBm at close range; it wasn't seen earlier, probably while off or asleep).
- Bonding/pairing: **not needed** for GATT enumeration or DIS reads. Whether NUS needs it is unknown.
