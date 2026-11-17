# Phase 0 hardware spike scripts

Throwaway scripts used to verify the M1 protocol (see `docs/hardware/m1-protocol.md`). They are **not** application code: they aren't linted, type-checked or tested, and the real implementation belongs in `src/` under #4/#5. Keep them for reproducing the observations in the protocol notes.

| Script | Touches device | What it does |
|---|---|---|
| `gatt.py` | read-only | Scan for `M1_*`, connect, list services, read Device Information (never the serial). Prints connect + discovery time. |
| `m1fetch.py` | allowlisted commands only | Status, disk space, `filelist.txt`, then the smallest and largest ride over YMODEM. `Probe._write` refuses any CTL opcode other than `ff`/`04`/`09`/`05` and any RX byte other than `C`/`ACK`/`NAK`/`CAN`. On a transfer error it sends `CAN` twice and re-checks status. |

```
uv run --with bleak python -I tools/spike/gatt.py
uv run --with bleak python -I tools/spike/m1fetch.py ~/m1-spike-out   # default: ~/.cache/cycplus-m1-studio/spike
```

- Ride data is personal (AGENTS.md rule 4). `m1fetch.py` refuses to write inside the repo.
- Wake the M1 first; it sleeps after about 10 minutes idle.
- Known open issue: the FIT fetch stalls after block 0, and the connection can then stay stuck. See "Open issue" in the protocol notes before running `m1fetch.py`.
