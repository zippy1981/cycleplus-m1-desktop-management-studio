# CYCPLUS M1 protocol notes

> **Status: unverified.** Nothing below has been confirmed on hardware yet. Per `AGENTS.md` rule 1, the opcode allowlist is empty until this file records observed behavior.

## Device identity

| Field | Value | Source |
|---|---|---|
| Advertised name | _TBD_ | |
| Firmware version | _TBD_ | DIS 0x2A26? |
| Model / manufacturer | _TBD_ | DIS 0x2A24 / 0x2A29? |

Never record the MAC address or serial number here.

## USB

- [ ] Plug in over USB-C on Linux and record `dmesg`, `lsusb`, and `lsblk` output (redact the serial number).
- [ ] Is it USB mass storage? If so, record the directory layout and FIT filenames.
- [ ] Is it read-only or writable? (Do not write to it to find out. Check the mount flags and the device docs.)

## BLE GATT layout

_Fill this in from `m1studio diag gatt` output (read-only enumeration)._

| Service UUID | Characteristic UUID | Properties | Observed purpose |
|---|---|---|---|

## Observed transfer protocol

Source: an HCI snoop capture of the official CYCPLUS phone app syncing a ride. Keep the raw capture out of the repo; commit only an anonymized summary.

## Opcode allowlist

| Opcode / write | Characteristic | Meaning | Destructive? | Evidence |
|---|---|---|---|---|
| — | — | — | — | — |

## Connection behavior

- Connect / disconnect / reconnect timing: _TBD_
- Does it advertise only in a sync/pairing mode? _TBD_
- Does it need bonding/pairing? _TBD_
