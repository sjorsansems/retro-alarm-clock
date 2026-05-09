#!/usr/bin/env python3
"""
gif_to_bin.py
Converteert een GIF-animatie naar .bin formaat (retro alarm klok formaat)

Gebruik:
    python gif_to_bin.py <naam>.gif

Output:
    <naam>.bin
"""
from PIL import Image
import struct
import sys
import os

W, H = 128, 64
FRAME_SIZE = W * H // 8  # 1024 bytes per frame


def img_to_vlsb(img: Image.Image) -> bytes:
    """PIL 'L' image -> MONO_VLSB bytes (MicroPython framebuf formaat)."""
    img2 = img.convert("L")
    buf = bytearray(FRAME_SIZE)
    px = img2.load()
    for y in range(H):
        for x in range(W):
            if px[x, y] > 127:
                buf[(y >> 3) * W + x] |= (1 << (y & 7))
    return bytes(buf)


def gif_to_bin(gif_path: str, bin_path: str = None) -> None:
    """Converteert GIF naar BIN formaat."""
    if not os.path.exists(gif_path):
        print(f"❌ Fout: {gif_path} niet gevonden")
        return
    
    if bin_path is None:
        name = os.path.splitext(gif_path)[0]
        bin_path = f"{name}.bin"
    
    try:
        gif = Image.open(gif_path)
    except Exception as e:
        print(f"❌ Fout bij openen GIF: {e}")
        return
    
    frames = []
    delays = []
    
    try:
        while True:
            # Resample naar 128x64 als nodig
            frame = gif.copy().convert("RGB")
            if frame.size != (W, H):
                frame = frame.resize((W, H), Image.Resampling.LANCZOS)
            
            # Converteer naar zwart-wit (1-bit)
            frames.append(img_to_vlsb(frame))
            
            # Zet delay (in ms)
            delay = gif.info.get("duration", 50)
            delays.append(delay)
            
            gif.seek(len(frames))
    except EOFError:
        pass  # Einde van GIF bereikt
    
    if not frames:
        print(f"❌ Geen frames gevonden in {gif_path}")
        return
    
    # Schrijf BIN bestand
    with open(bin_path, "wb") as f:
        # Header: magic bytes
        f.write(bytes([0x47, 0xAF]))
        
        # Aantal frames
        f.write(struct.pack(">H", len(frames)))
        
        # Afmetingen
        f.write(bytes([W, H]))
        
        # Delays (ms per frame, big-endian 16-bit)
        for delay in delays:
            f.write(struct.pack(">H", delay))
        
        # Frame data
        for frame in frames:
            f.write(frame)
    
    kb = os.path.getsize(bin_path) / 1024
    print(f"✓ Geconverteerd: {gif_path}")
    print(f"  → {bin_path}")
    print(f"  Frames: {len(frames)}")
    print(f"  Grootte: {kb:.1f} KB")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python gif_to_bin.py <naam>.gif [output.bin]")
        sys.exit(1)
    
    gif_file = sys.argv[1]
    bin_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    gif_to_bin(gif_file, bin_file)
