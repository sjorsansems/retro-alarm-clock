"""
gif_to_frames.py  –  GIF → MicroPython frames converter
=========================================================
Draait lokaal op de PC (niet op de ESP32).

Gebruik:
    pip install Pillow
    python tools/gif_to_frames.py mijn_animatie.gif

Opties:
    --out  NAAM     Uitvoerbestand (default: <naam>_frames.py of .bin)
    --w    BREEDTE  Target breedte  (default: 128)
    --h    HOOGTE   Target hoogte   (default: 64)
    --thr  DREMPEL  Wit/zwart drempel 0-255 (default: 128)
    --inv           Inverteer kleuren (wit ↔ zwart)
    --dither        Gebruik Floyd-Steinberg dithering ipv harde drempel
    --bin           Schrijf compact binair .bin bestand ipv Python
    --max  N        Maximaal N frames bewaren (default: 200)

Formaat keuze:
    Klein/weinig frames (≤30):  Python .py  – makkelijk, alles in RAM
    Groot/veel frames  (>30):   Binair .bin – 6× kleiner, streaming van flash

Binair formaat (gif_player.py leest dit automatisch):
    Byte 0-1:  magic 0xGF 0xAF
    Byte 2-3:  aantal frames (uint16 big-endian)
    Byte 4:    breedte
    Byte 5:    hoogte
    Byte 6..(6+n*2-1):  delays in ms per frame (uint16 big-endian)
    Rest:      frame data aaneengesloten (width*height//8 bytes per frame)
"""

import sys
import os
import argparse

try:
    from PIL import Image
except ImportError:
    print("Pillow niet gevonden. Installeer met:  pip install Pillow")
    sys.exit(1)


def image_to_mono_vlsb(img, width, height, threshold, invert, dither, crop=None):
    """Converteer PIL Image naar MONO_VLSB bytearray (MicroPython framebuf formaat)."""
    # Schaal naar doelresolutie
    img = img.convert("RGBA")  # GIF kan transparantie hebben
    background = Image.new("RGBA", img.size, (0, 0, 0, 255))
    background.paste(img, mask=img.split()[3])  # alpha compositing op zwart
    img = background.convert("L")              # grijs

    if crop:
        img = img.crop(crop)  # (left, top, right, bottom) in bronpixels

    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)

    if dither:
        # Floyd-Steinberg via Pillow
        img = img.convert("1", dither=Image.FLOYDSTEINBERG)
        get_pixel = lambda x, y: 255 if img.getpixel((x, y)) else 0
    else:
        pixels = img.load()
        get_pixel = lambda x, y: pixels[x, y]

    buf = bytearray(height // 8 * width)
    for y in range(height):
        for x in range(width):
            v = get_pixel(x, y)
            lit = (v > threshold) if not invert else (v <= threshold)
            if lit:
                buf[(y >> 3) * width + x] |= (1 << (y & 7))
    return bytes(buf)


def extract_gif_frames(path, width, height, threshold, invert, dither, crop=None):
    frames = []
    delays = []

    gif = Image.open(path)
    try:
        while True:
            # Haal frame-delay op uit GIF metadata (in centiseconden)
            info = gif.info
            delay_cs = info.get("duration", 100)   # ms in Pillow (nieuwere versies)
            # Pillow geeft duration al in ms; minimum 20ms om flicker te vermijden
            delay_ms = max(20, int(delay_cs))

            frame_buf = image_to_mono_vlsb(gif, width, height, threshold, invert, dither, crop)
            frames.append(frame_buf)
            delays.append(delay_ms)

            gif.seek(gif.tell() + 1)
    except EOFError:
        pass

    return frames, delays


# Drempelwaarden voor aanbevelingen
WARN_FRAMES_PY  = 30    # boven dit aantal: waarschuw voor .py formaat
WARN_KB_FLASH   = 200   # boven dit KB: waarschuw voor flash gebruik


def write_output_py(frames, delays, width, height, out_path):
    """Schrijf frames als Python-lijst (alles in RAM op ESP32)."""
    total_bytes = len(frames) * width * height // 8
    with open(out_path, "w") as f:
        f.write("# Automatisch gegenereerd door gif_to_frames.py\n")
        f.write("# Pas dit bestand niet handmatig aan.\n\n")
        f.write(f"WIDTH  = {width}\n")
        f.write(f"HEIGHT = {height}\n")
        f.write(f"DELAYS = {delays}\n\n")
        f.write("FRAMES = [\n")
        for i, frame in enumerate(frames):
            hex_str = ", ".join(f"0x{b:02X}" for b in frame)
            f.write(f"    bytes([{hex_str}]),  # frame {i}\n")
        f.write("]\n")
    file_kb = os.path.getsize(out_path) // 1024
    print(f"  Geschreven: {out_path}  ({file_kb}KB op schijf, {total_bytes // 1024}KB raw data)")
    if total_bytes > WARN_KB_FLASH * 1024:
        print(f"  ⚠ Let op: {total_bytes // 1024}KB raw in RAM — kan te groot zijn voor ESP32.")
        print(f"    Gebruik --bin voor streaming-modus.")


def write_output_bin(frames, delays, width, height, out_path):
    """Schrijf frames als compact binair bestand (streaming op ESP32)."""
    n = len(frames)
    frame_size = width * height // 8
    with open(out_path, "wb") as f:
        # Header: magic 0x47 ('G') + 0xAF
        f.write(bytes([0x47, 0xAF]))
        f.write(n.to_bytes(2, "big"))
        f.write(bytes([width, height]))
        # Delay tabel
        for d in delays:
            f.write(d.to_bytes(2, "big"))
        # Frame data
        for frame in frames:
            f.write(frame)
    file_kb = os.path.getsize(out_path) // 1024
    print(f"  Geschreven: {out_path}  ({file_kb}KB)  — streaming-modus")
    print(f"  RAM gebruik op ESP32: ~{frame_size} bytes (1 frame tegelijk)")


def write_output(frames, delays, width, height, out_path, use_bin):
    total_bytes = len(frames) * width * height // 8
    print(f"  {len(frames)} frames, {total_bytes // 1024}KB raw data")
    if use_bin:
        write_output_bin(frames, delays, width, height, out_path)
    else:
        write_output_py(frames, delays, width, height, out_path)


def main():
    parser = argparse.ArgumentParser(description="GIF → MicroPython MONO_VLSB frames")
    parser.add_argument("gif", help="Pad naar het GIF-bestand")
    parser.add_argument("--out", default=None, help="Uitvoerbestand")
    parser.add_argument("--w",   type=int, default=128, help="Breedte (default: 128)")
    parser.add_argument("--h",   type=int, default=64,  help="Hoogte  (default: 64)")
    parser.add_argument("--thr", type=int, default=128, help="Drempel 0-255 (default: 128)")
    parser.add_argument("--inv", action="store_true",   help="Inverteer kleuren")
    parser.add_argument("--dither", action="store_true", help="Floyd-Steinberg dithering")
    parser.add_argument("--bin", action="store_true",   help="Compact binair .bin bestand (aanbevolen bij >30 frames)")
    parser.add_argument("--max", type=int, default=200, help="Max aantal frames (default: 200)")
    parser.add_argument("--crop", type=int, nargs=4, metavar=("L","T","R","B"),
                        help="Bijsnijden bronafbeelding: links boven rechts onder (in pixels)")
    args = parser.parse_args()

    if not os.path.isfile(args.gif):
        print(f"Bestand niet gevonden: {args.gif}")
        sys.exit(1)

    out_path = args.out
    if out_path is None:
        base = os.path.splitext(os.path.basename(args.gif))[0]
        ext  = ".bin" if args.bin else "_frames.py"
        out_path = f"{base}{ext}"

    crop = tuple(args.crop) if args.crop else None
    if crop:
        print(f"  Crop: {crop[0]},{crop[1]} → {crop[2]},{crop[3]} (bronpixels)")

    print(f"Inlezen: {args.gif}")
    frames, delays = extract_gif_frames(
        args.gif, args.w, args.h, args.thr, args.inv, args.dither, crop
    )
    total = len(frames)
    print(f"  GIF heeft {total} frames")
    print(f"  Frame-delays: {delays[:8]}{'...' if total > 8 else ''}")

    # Auto-advies: stel --bin voor bij grote GIFs
    raw_kb = total * args.w * args.h // 8 // 1024
    if not args.bin and total > WARN_FRAMES_PY:
        print(f"  ⚠ {total} frames = ~{raw_kb}KB in RAM op ESP32.")
        print(f"    Aanbeveling: gebruik --bin voor streaming (6× kleiner, RAM-vriendelijk).")

    # Frame-limiet toepassen
    if total > args.max:
        print(f"  ✂ Afgekapt tot {args.max} frames (was {total}). Gebruik --max N voor meer.")
        frames = frames[:args.max]
        delays = delays[:args.max]

    write_output(frames, delays, args.w, args.h, out_path, args.bin)
    print()
    dest = os.path.basename(out_path)
    print("Kopieer naar ESP32:")
    print(f"  mpremote connect COM7 cp {out_path} :{dest} + cp gif_player.py :gif_player.py")


if __name__ == "__main__":
    main()
