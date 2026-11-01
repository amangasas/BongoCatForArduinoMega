
from PIL import Image
from pathlib import Path
import struct

INPUTS = ["Pet1.png", "Pet2.png"]
OUTPUT_SIZE = (64, 64)

# Set this to the background color used by your sprites.
BACKGROUND = (255, 255, 255)

def rgb888_to_rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

for filename in INPUTS:
    image = Image.open(filename).convert("RGBA")
    image.thumbnail(OUTPUT_SIZE, Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", OUTPUT_SIZE, (*BACKGROUND, 255))

    x = (OUTPUT_SIZE[0] - image.width) // 2
    y = (OUTPUT_SIZE[1] - image.height) // 2

    canvas.alpha_composite(image, (x, y))

    pixels = canvas.convert("RGB").load()
    output = bytearray()

    for y in range(64):
        for x in range(64):
            r, g, b = pixels[x, y]
            value = rgb888_to_rgb565(r, g, b)
            output.extend(struct.pack("<H", value))

    output_name = Path(filename).stem.upper() + ".RGB"
    Path(output_name).write_bytes(output)

    print(f"{output_name}: {len(output)} bytes")
