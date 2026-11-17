"""Read-only M1 probe: status, disk space, filelist.txt, then smallest + largest FIT via YMODEM.
All writes go through Probe._write, which enforces the allowlist.

Output (ride list + FIT files = personal data) goes OUTSIDE the repo:
  argv[1] if given, else ~/.cache/cycplus-m1-studio/spike
Run:  uv run --with bleak python -I tools/spike/m1fetch.py [OUT_DIR]
"""
import asyncio, sys, time, re, hashlib, pathlib
from bleak import BleakScanner, BleakClient

CTL = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"; RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"; TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
SOH, STX, EOT, ACK, NAK, CAN, C = 0x01, 0x02, 0x04, 0x06, 0x15, 0x18, 0x43
ALLOWED_CTL = {0xFF, 0x04, 0x09, 0x05}
ALLOWED_RX = {bytes([x]) for x in (C, ACK, NAK, CAN)}
NAME_RE = re.compile(r"^(filelist\.txt|\d{14}\.fit)$")
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path.home() / ".cache/cycplus-m1-studio/spike").expanduser()
if (pathlib.Path(__file__).resolve().parents[2] / ".git").exists() and OUT.resolve().is_relative_to(pathlib.Path(__file__).resolve().parents[2]):
    sys.exit(f"refusing to write ride data inside the repo: {OUT}")
OUT.mkdir(parents=True, exist_ok=True)

def xor8(b):
    x = 0
    for v in b: x ^= v
    return x
def crc16_arc(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8): crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc
def cmd(op, payload=b""):
    body = bytes([op]) + payload; return body + bytes([xor8(body)])
assert cmd(0x05, b"filelist.txt")[-1] == 0x57 and crc16_arc(b"123456789") == 0xBB3D

class Probe:
    def __init__(s, c): s.c, s.q, s.tx, s.ev, s.log, s.sizes = c, asyncio.Queue(), bytearray(), asyncio.Event(), [], []
    async def _write(s, uuid, data):
        if uuid == CTL:
            if data[0] not in ALLOWED_CTL or xor8(data[:-1]) != data[-1]: raise PermissionError(f"CTL {data.hex()} refused")
            if data[0] == 0x05 and not NAME_RE.match(data[1:-1].decode()): raise PermissionError("fetch name refused")
        elif uuid != RX or data not in ALLOWED_RX: raise PermissionError(f"write {uuid[4:8]} {data.hex()} refused")
        s.log.append(("->", uuid[4:8], data.hex()[:40])); await s.c.write_gatt_char(uuid, data, response=False)
    def on_ctl(s, _, d): s.log.append(("<-ctl", bytes(d[:24]).hex())); s.q.put_nowait(bytes(d))
    def on_tx(s, _, d): s.sizes.append(len(d)); s.tx.extend(d); s.ev.set()
    async def ctl(s, op, payload=b"", timeout=5.0):
        while not s.q.empty(): s.q.get_nowait()
        await s._write(CTL, cmd(op, payload)); return await asyncio.wait_for(s.q.get(), timeout)
    async def need(s, n, timeout=10.0):
        end = time.monotonic() + timeout
        while len(s.tx) < n:
            s.ev.clear(); rem = end - time.monotonic()
            try:
                if rem <= 0: raise TimeoutError
                await asyncio.wait_for(s.ev.wait(), rem)
            except TimeoutError:
                raise TimeoutError(f"need {n} have {len(s.tx)} head={bytes(s.tx[:6]).hex()} tail={bytes(s.tx[-6:]).hex()} "
                                   f"notif_sizes_last={s.sizes[-10:]} n_notif={len(s.sizes)}") from None
    async def block(s):
        await s.need(1); h = s.tx[0]
        if h == EOT: del s.tx[:1]; return "EOT", None, None
        if h not in (SOH, STX): raise ValueError(f"bad header {h:#x} buf={bytes(s.tx[:12]).hex()} len={len(s.tx)}")
        size = 128 if h == SOH else 1024; tot = size + 5
        await s.need(tot); b = bytes(s.tx[:tot]); del s.tx[:tot]
        ok = (b[1] ^ b[2]) == 0xFF and crc16_arc(b[3:3 + size]) == int.from_bytes(b[-2:], "big")
        return ("SOH" if h == SOH else "STX"), b[1], (b[3:3 + size] if ok else None)
    async def fetch(s, name):
        r = await s.ctl(0x05, name.encode())
        if r != cmd(0x06, name.encode()): print("  fetch refused by device:", r.hex()); return None
        s.tx.clear(); s.sizes.clear()
        try:
            await s._write(RX, bytes([C]))
            k, n, d = await s.block()
            if d is None or n != 0: raise ValueError(f"block0 bad {k} {n}")
            fname, fsize = d.rstrip(b"\0").decode().split()[:2]; fsize = int(fsize)
            await s._write(RX, bytes([ACK])); await s._write(RX, bytes([C]))
            out, seq, kinds, naks = bytearray(), 1, [], 0
            while True:
                k, n, d = await s.block()
                if k == "EOT":
                    await s._write(RX, bytes([NAK])); k2, _, _ = await s.block(); await s._write(RX, bytes([ACK])); break
                kinds.append(k)
                if d is None:
                    naks += 1
                    if naks > 5: raise ValueError("too many CRC errors")
                    await s._write(RX, bytes([NAK])); continue
                if n == (seq - 1) & 0xFF: await s._write(RX, bytes([ACK])); continue
                if n != seq & 0xFF: raise ValueError(f"seq {n} != {seq}")
                out += d; seq += 1; await s._write(RX, bytes([ACK]))
            try: idle = (await asyncio.wait_for(s.q.get(), 5)).hex()
            except asyncio.TimeoutError: idle = "none"
            print(f"  blocks={len(kinds)} {dict((x, kinds.count(x)) for x in set(kinds))} naks={naks} "
                  f"received={len(out)} declared={fsize} second_eot={k2 == 'EOT'} idle_after={idle}")
            if len(out) < fsize: raise ValueError("short transfer")
            return bytes(out[:fsize])
        except Exception as e:
            print("  TRANSFER FAILED:", e)
            for _ in range(2): await s._write(RX, bytes([CAN])); await asyncio.sleep(0.2)
            await asyncio.sleep(1.0)
            try: print("  after CAN, status:", (await s.ctl(0xFF, b"\0")).hex())
            except Exception as e2: print("  after CAN, status: no reply", e2)
            print("  wire tail:", s.log[-10:]); return None

async def main():
    d = await BleakScanner.find_device_by_filter(lambda d, a: (a.local_name or "").startswith("M1_"), timeout=15)
    if not d: print("M1 not found"); return 2
    async with BleakClient(d, timeout=40) as c:
        try: await c._backend._acquire_mtu()
        except Exception as e: print("mtu acquire failed:", e)
        print("MTU:", c.mtu_size)
        p = Probe(c); await c.start_notify(CTL, p.on_ctl); await c.start_notify(TX, p.on_tx); await asyncio.sleep(1)
        try:
            r = await p.ctl(0xFF, b"\0"); print("status:", r.hex())
            if r[:1] != b"\x04": print("force idle:", (await p.ctl(0x04, b"\0")).hex())
            r = await p.ctl(0x09, b"\0"); print("diskspace:", r[1:-1].decode(errors="replace"), "crc_ok", xor8(r) == 0)
            print("fetch filelist.txt"); fl = await p.fetch("filelist.txt")
            if fl is None: return 1
            (OUT / "filelist.txt").write_bytes(fl)
            ents = sorted(((l.split()[0], int(l.split()[-1])) for l in fl.decode().splitlines()
                           if len(l.split()) >= 2 and NAME_RE.match(l.split()[0]) and l.split()[-1].isdigit()), key=lambda e: e[1])
            print(f"  {len(ents)} rides listed")
            for i, (name, listed) in enumerate([ents[0], ents[-1]]):
                await asyncio.sleep(1)
                r = await p.ctl(0xFF, b"\0")
                print(f"[{i}] status {r.hex()}; fetch ride of listed size {listed}")
                t0 = time.monotonic(); data = await p.fetch(name); dt = time.monotonic() - t0
                if data is None: return 1
                (OUT / f"ride{i}.fit").write_bytes(data)
                print(f"[{i}] got={len(data)} listed_match={len(data) == listed} {dt:.1f}s {len(data)/dt/1024:.1f} KiB/s "
                      f"sha256={hashlib.sha256(data).hexdigest()[:12]}…")
        finally:
            if c.is_connected:          # after a disconnect, stop_notify raises and hides the real error
                for u in (CTL, TX):
                    try: await c.stop_notify(u)
                    except Exception as e: print("stop_notify failed:", e)
            else:
                print("DISCONNECTED during session; wire tail:", p.log[-10:])
sys.exit(asyncio.run(main()) or 0)
