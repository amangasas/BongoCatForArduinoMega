
#!/usr/bin/env python3
"""
Bongo Cat -> Arduino Mega sprite converter

Run from the root of the original bongo_cat_monitor repository:
    py sprite_converter.py

Reads LVGL RGB565A8 C sprites and composites them into:
    output_frames/*.RGB   64x64 RGB565, little-endian
    output_frames/*.png   preview images

Each .RGB file is exactly 8192 bytes.
"""

from pathlib import Path
import re
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output_frames"

SPRITES = {
    "body": {
        "normal": "animations/body/standardbody1.c",
        "ear": "animations/body/bodyeartwitch.c",
    },
    "faces": {
        "normal": "animations/faces/stock_face.c",
        "happy": "animations/faces/happy_face.c",
        "blink": "animations/faces/blink_face.c",
        "sleepy": "animations/faces/sleepy_face.c",
    },
    "paws": {
        "left": "animations/paws/leftpawdown.c",
        "right": "animations/paws/rightpawdown.c",
        "up": "animations/paws/twopawsup.c",
    },
    "table": {
        "normal": "animations/table/table1.c",
    },
    "effects": {
        "left_click": "animations/effects/left_click_effect.c",
        "right_click": "animations/effects/right_click_effect.c",
        "sleepy1": "animations/effects/sleepy1.c",
        "sleepy2": "animations/effects/sleepy2.c",
        "sleepy3": "animations/effects/sleepy3.c",
    },
}


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def read_sprite(path_string: str) -> Image.Image:
    path = ROOT / path_string

    if not path.is_file():
        raise FileNotFoundError(f"Missing sprite file: {path}")

    source = strip_comments(path.read_text(encoding="utf-8", errors="replace"))

    # Find the LVGL pixel array.
    array_match = re.search(
        r"\b([A-Za-z_]\w*)_map\s*\[\s*\]\s*=\s*\{(.*?)\}\s*;",
        source,
        flags=re.S,
    )

    if not array_match:
        raise ValueError(f"Could not find the *_map[] array in {path}")

    sprite_name = array_match.group(1)
    array_text = array_match.group(2)

    # The source arrays contain byte values such as 0x00 and 0xff.
    byte_tokens = re.findall(
        r"(?<![A-Za-z0-9_])(?:0[xX][0-9A-Fa-f]+|\d+)(?![A-Za-z0-9_])",
        array_text,
    )
    raw = bytes(int(token, 0) & 0xFF for token in byte_tokens)

    # Read the dimensions from the LVGL image descriptor.
    descriptor_match = re.search(
        rf"\bconst\s+lv_img_dsc_t\s+{re.escape(sprite_name)}\s*=\s*"
        rf"\{{\s*\{{\s*LV_IMG_CF_RGB565A8\s*,\s*\d+\s*,\s*\d+\s*,"
        rf"\s*(\d+)\s*,\s*(\d+)\s*\}}\s*,\s*(\d+)\s*,",
        source,
        flags=re.S,
    )

    if not descriptor_match:
        raise ValueError(
            f"Could not find an RGB565A8 LVGL descriptor for {sprite_name} in {path}"
        )

    width = int(descriptor_match.group(1))
    height = int(descriptor_match.group(2))
    declared_size = int(descriptor_match.group(3))

    pixel_count = width * height
    expected_size = pixel_count * 3

    if declared_size != expected_size:
        raise ValueError(
            f"{path}: descriptor says {declared_size} bytes, "
            f"but {width}x{height} RGB565A8 requires {expected_size}"
        )

    if len(raw) != declared_size:
        raise ValueError(
            f"{path}: parsed {len(raw)} bytes, descriptor says {declared_size}. "
            "The source array format may have changed."
        )

    # LVGL RGB565A8 layout:
    #   first width*height*2 bytes = RGB565 pixels
    #   final width*height bytes   = alpha values
    color_data = raw[: pixel_count * 2]
    alpha_data = raw[pixel_count * 2 :]

    rgba = Image.new("RGBA", (width, height))
    pixels = []

    for i in range(pixel_count):
        lo = color_data[i * 2]
        hi = color_data[i * 2 + 1]
        color = lo | (hi << 8)

        red5 = (color >> 11) & 0x1F
        green6 = (color >> 5) & 0x3F
        blue5 = color & 0x1F

        red = (red5 * 255 + 15) // 31
        green = (green6 * 255 + 31) // 63
        blue = (blue5 * 255 + 15) // 31

        pixels.append((red, green, blue, alpha_data[i]))

    rgba.putdata(pixels)
    print(f"Loaded {path_string}: {width}x{height}, {len(raw)} bytes")
    return rgba


def composite(*layers: Image.Image | None) -> Image.Image:
    result = Image.new("RGBA", (64, 64), (255, 255, 255, 255))

    for layer in layers:
        if layer is None:
            continue

        if layer.size != (64, 64):
            raise ValueError(
                f"Expected a 64x64 layer, got {layer.width}x{layer.height}"
            )

        result = Image.alpha_composite(result, layer)

    # The TFT background is white, so transparency is flattened to white.
    background = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    return Image.alpha_composite(background, result).convert("RGB")


def save_frame(name: str, image: Image.Image) -> None:
    if image.size != (64, 64):
        raise ValueError(f"{name}: wrong output size {image.size}")

    OUTPUT.mkdir(parents=True, exist_ok=True)

    # Keep a PNG preview for checking the composition on the PC.
    image.save(OUTPUT / f"{name}.png")

    # Arduino file format: 4096 RGB565 pixels, little-endian.
    output = bytearray()

    for red, green, blue in image.getdata():
        r5 = red >> 3
        g6 = green >> 2
        b5 = blue >> 3
        rgb565 = (r5 << 11) | (g6 << 5) | b5

        output.append(rgb565 & 0xFF)
        output.append((rgb565 >> 8) & 0xFF)

    output_path = OUTPUT / f"{name}.RGB"
    output_path.write_bytes(output)

    if len(output) != 8192:
        raise RuntimeError(f"{name}: output size is {len(output)}, not 8192")


def main() -> int:
    print("\n=== Bongo Cat sprite converter ===\n")

    loaded = {}

    for category, entries in SPRITES.items():
        loaded[category] = {}

        for key, path in entries.items():
            loaded[category][key] = read_sprite(path)

    body = loaded["body"]
    faces = loaded["faces"]
    paws = loaded["paws"]
    table = loaded["table"]["normal"]
    effects = loaded["effects"]

    # The original firmware draws layers in this exact order:
    # body -> face -> table -> paws -> effects.
    def make(
        name: str,
        body_layer: Image.Image,
        face: Image.Image,
        paw: Image.Image | None,
        effect: Image.Image | None = None,
    ) -> None:
        save_frame(name, composite(body_layer, face, table, paw, effect))

    # Idle poses.
    make("IDLE1", body["normal"], faces["normal"], paws["up"])
    make("IDLE2", body["normal"], faces["normal"], None)
    make("IDLE3", body["normal"], faces["sleepy"], None)

    # The three sleepy-effect frames.
    make("SLEEP1", body["normal"], faces["sleepy"], None, effects["sleepy1"])
    make("SLEEP2", body["normal"], faces["sleepy"], None, effects["sleepy2"])
    make("SLEEP3", body["normal"], faces["sleepy"], None, effects["sleepy3"])

    # Blink and ear twitch.
    make("BLINK", body["normal"], faces["blink"], paws["up"])
    make("EAR", body["ear"], faces["normal"], paws["up"])

    # Normal typing poses.
    make("TYPE_L", body["normal"], faces["normal"], paws["left"])
    make("TYPE_UP", body["normal"], faces["normal"], paws["up"])
    make("TYPE_R", body["normal"], faces["normal"], paws["right"])

    # Fast typing poses with the original click effects.
    make("FAST_L", body["normal"], faces["normal"], paws["left"], effects["left_click"])
    make("FAST_UP", body["normal"], faces["normal"], paws["up"])
    make("FAST_R", body["normal"], faces["normal"], paws["right"], effects["right_click"])

    # Streak poses: happy face plus alternating paws.
    make("HAPPY_L", body["normal"], faces["happy"], paws["left"], effects["left_click"])
    make("HAPPY_UP", body["normal"], faces["happy"], paws["up"])
    make("HAPPY_R", body["normal"], faces["happy"], paws["right"], effects["right_click"])

    print("\nConversion complete.")
    print(f"Output folder: {OUTPUT}")
    print("Copy every *.RGB file into the SD card's /FRAMES/ directory.")
    print("Each frame is 8192 bytes (64x64 RGB565, little-endian).")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
