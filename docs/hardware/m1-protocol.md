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

## Transfer protocol: YMODEM over NUS (from prior art; unverified on our M1)

The M1 belongs to the XOSS/Xingzhe device family: same manufacturer string, same GATT map, M2 on firmware V1.4.0 vs our M1 on V1.4.1. These devices speak a vendor-documented protocol, with commands on `6e400004` (CTL) and **YMODEM** file transfer on RX (`…0002`) / TX (`…0003`).

### Prior art (all MIT, so porting into this GPL-3.0 project with attribution is fine)

| Source | Device | Quality notes |
|---|---|---|
| [ekspla/xoss_sync](https://github.com/ekspla/xoss_sync) | XOSS G+ | **Best reference.** Verifies CRC16/ARC per block, truncates to the size from block 0, and checks the CTL crc8. Cites the vendor spec at `developer.imxingzhe.com/docs/device/tracking_data_service/` (couldn't reach it from here). |
| [andrewkomkov/cycplus-m2-sync](https://github.com/andrewkomkov/cycplus-m2-sync) `docs/PROTOCOL.md` | CYCPLUS M2 FW V1.4.0 | Best write-up: command table plus model quirks. Lists M1 as "expected to work". |
| [thefellaguy/cycplusSync](https://github.com/thefellaguy/cycplusSync) | **CYCPLUS M1** | Shows the M1 works with this protocol (name `M1_XXXX`, 16 MB storage, `YYYYMMDDhhmmss.fit` names). **Do not copy its transfer logic:** it strips trailing `0x00` instead of truncating to the block-0 size, skips CRC checks, and relies on timing. Its own log shows saved sizes differing from received sizes, which breaks rule 3 (original bytes unchanged). |
| [Kaiserdragon2/CycSync](https://github.com/Kaiserdragon2/CycSync) | CYCPLUS M2 | Origin of the M1 script |

### CTL commands (`6e400004`, write; replies arrive as notifications on the same characteristic)

`crc8` = XOR of all preceding bytes. `<name>` = ASCII filename.

| Bytes → | ← Reply | Meaning | Class |
|---|---|---|---|
| `ff 00 ff` | `04` or `04 00 04` | Status request; `04` = idle | read-only |
| `04 00 04` | `04…` | Force idle | state reset, non-destructive |
| `09 00 09` | `0a "<free>/<total>" crc8` | Free / total storage in KB | read-only |
| `05 <name> crc8` | `06 <name> crc8` | Fetch file; YMODEM follows on RX/TX | read-only |
| `07 <name> crc8` | `08 <name> crc8` | **Send file to device** | ⛔ **writes device storage** |
| `0d <name> crc8` | `0e …` | **Delete file** | ⛔ **destructive** |
| `54 <unix LE32> crc8` | `55 …` | Set clock | mutating (benign, but needs user opt-in) |
| `1f 00 1f` | | Stop | unknown; don't use |
| ← `11/12/13/14/15 …` | | Errors: command, file N/A, memory, not idle, parse | |

### YMODEM receive (RX = host→device, TX = device→host)

1. Send `C` (`0x43`).
2. Block 0 arrives: `SOH 00 FF "<name> <size>"` zero-padded, then CRC16. **The size here is authoritative.**
3. Send `ACK` then `C`. Data blocks follow: `SOH` (128 B) or `STX` (1024 B), `num`, `~num`, data, CRC16. Size each block from its first byte.
4. Send `ACK` for each good block and `NAK` to request a resend. Send `CAN` (`0x18`) to abort.
5. The device sends `EOT`; reply `NAK`; it sends `EOT` again; reply `ACK`, and the device returns to idle.
6. CRC is **CRC16/ARC** (poly 0xA001, reflected), not CRC16/XMODEM. Truncate the payload to the block-0 size, then SHA-256 it.

The ride index is `filelist.txt` (`name size` per line). Newer XOSS models use `workouts.json` instead; handle both.

MTU matters: the M2 negotiates 185 and switches to STX blocks (about 13 s for 228 KB), while MTU 23 takes minutes. **Measure the M1's negotiated MTU.**

## Connection behavior

- Connect / disconnect / reconnect timing: _TBD_
- Advertises while powered on: **yes** (seen at -34 dBm at close range; it wasn't seen earlier, probably while off or asleep).
- Bonding/pairing: **not needed** for GATT enumeration or DIS reads. Whether NUS needs it is unknown.
