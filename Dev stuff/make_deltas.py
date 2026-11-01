#!/usr/bin/env python3
"""Generate precomputed row-span RGB565 deltas for BongoMega_v05.

Input: 17 full 64x64 RGB565 little-endian .RGB files in FRAMES/.
Output: DELTAS/00_01.DLT, etc. Copy DELTAS/ to the SD card root.

Each DLT contains 64 row records:
  uint8 start_x, uint8 pixel_count, then pixel_count RGB565-LE pixels.
An unchanged row is: 0xFF, 0x00.
"""
from pathlib import Path
import sys

FRAME_NAMES = [
    "IDLE1", "IDLE2", "IDLE3",
    "SLEEP1", "SLEEP2", "SLEEP3",
    "BLINK", "EAR",
    "TYPE_L", "TYPE_UP", "TYPE_R",
    "FAST_L", "FAST_UP", "FAST_R",
    "HAPPY_L", "HAPPY_UP", "HAPPY_R",
    "Pet1", "Pet2",
]

WIDTH = 64
HEIGHT = 64
FRAME_BYTES = WIDTH * HEIGHT * 2


def make_delta(old: bytes, new: bytes) -> bytes:
    result = bytearray()
    for y in range(HEIGHT):
        row_start = y * WIDTH * 2
        old_row = old[row_start:row_start + WIDTH * 2]
        new_row = new[row_start:row_start + WIDTH * 2]

        first = -1
        last = -1
        for x in range(WIDTH):
            p = x * 2
            if old_row[p:p + 2] != new_row[p:p + 2]:
                if first < 0:
                    first = x
                last = x

        if first < 0:
            result.extend((255, 0))
        else:
            count = last - first + 1
            result.extend((first, count))
            result.extend(new_row[first * 2:(last + 1) * 2])

    return bytes(result)


def main():
    if len(sys.argv) >= 2:
        frames_dir = Path(sys.argv[1]).expanduser().resolve()
    else:
        entered = input("Path to the FRAMES folder: ").strip().strip('"')
        frames_dir = Path(entered).expanduser().resolve()

    if not frames_dir.is_dir():
        raise SystemExit(f"ERROR: FRAMES folder not found: {frames_dir}")

    output_dir = frames_dir.parent / "DELTAS"
    output_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    for name in FRAME_NAMES:
        path = frames_dir / f"{name}.RGB"
        if not path.is_file():
            raise SystemExit(f"ERROR: Missing frame: {path}")
        data = path.read_bytes()
        if len(data) != FRAME_BYTES:
            raise SystemExit(
                f"ERROR: {path.name} is {len(data)} bytes; expected {FRAME_BYTES}"
            )
        frames.append(data)

    # Remove only old generated DLT files, not other files in the directory.
    for old_file in output_dir.glob("*.DLT"):
        old_file.unlink()

    generated = 0
    omitted = 0
    total_bytes = 0
    largest = (0, "")

    for old_id, old_frame in enumerate(frames):
        for new_id, new_frame in enumerate(frames):
            if old_id == new_id:
                continue

            delta = make_delta(old_frame, new_frame)
            filename = f"{old_id:02d}_{new_id:02d}.DLT"

            # A delta >= a full 8192-byte frame is not worth storing.
            # The Mega automatically falls back to the full RGB file.
            if len(delta) >= FRAME_BYTES:
                omitted += 1
                continue

            (output_dir / filename).write_bytes(delta)
            generated += 1
            total_bytes += len(delta)
            if len(delta) > largest[0]:
                largest = (len(delta), filename)

    print("\nDelta generation complete")
    print(f"Input frames:       {len(frames)}")
    print(f"Generated deltas:   {generated}")
    print(f"Omitted (too large):{omitted}")
    print(f"Total delta data:   {total_bytes:,} bytes ({total_bytes / 1024:.1f} KiB)")
    if largest[1]:
        print(f"Largest delta:      {largest[1]} ({largest[0]:,} bytes)")
    print(f"Output folder:      {output_dir}")
    print("\nCopy the entire DELTAS folder to the ROOT of the SD card.")
    print("Keep the existing FRAMES folder unchanged; it is used as fallback.")


if __name__ == "__main__":
    main()
