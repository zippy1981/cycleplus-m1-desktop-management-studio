# Read-only: scan, connect, list services, read only DIS (0x180A); never the serial number.
# Run: uv run --with bleak python -I tools/spike/gatt.py
import asyncio, time
from bleak import BleakScanner, BleakClient
DIS = "0000180a-0000-1000-8000-00805f9b34fb"
async def main():
    t0 = time.monotonic()
    d = await BleakScanner.find_device_by_filter(lambda d, a: (a.local_name or "").startswith("M1_"), timeout=15)
    if not d: print("M1 not found"); return
    print(f"found after {time.monotonic()-t0:.1f}s")
    t1 = time.monotonic()
    async with BleakClient(d, timeout=40) as c:
        print(f"connected + services resolved in {time.monotonic()-t1:.1f}s")
        print("services:", [s.uuid[4:8] for s in c.services])
        for ch in c.services.get_service(DIS).characteristics:
            if ch.uuid.startswith("00002a25"): continue          # serial: never read/log
            print(" ", ch.description, (await c.read_gatt_char(ch)).decode(errors="replace"))
asyncio.run(main())
