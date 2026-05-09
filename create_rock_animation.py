#!/usr/bin/env python3
"""
Generate a high-contrast Rock animation GIF for OLED/GIF->BIN conversion.
The animation combines animated equalizer bars, a scrolling title, and flashes.
"""
from PIL import Image, ImageDraw
import os

WIDTH = 128
HEIGHT = 64
FRAMES = 40
FILENAME = "rock.gif"

frames = []

for frame_idx in range(FRAMES):
    img = Image.new("RGB", (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Stage border for retro concert-screen look.
    draw.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline=(160, 160, 160))

    # Top moving spotlights.
    spot_x = (frame_idx * 9) % WIDTH
    draw.polygon([(spot_x, 2), (spot_x - 12, 24), (spot_x + 12, 24)], fill=(80, 80, 80))
    spot_x2 = (WIDTH - 1) - ((frame_idx * 7) % WIDTH)
    draw.polygon([(spot_x2, 2), (spot_x2 - 10, 20), (spot_x2 + 10, 20)], fill=(60, 60, 60))

    # Equalizer bars.
    base_y = HEIGHT - 6
    bar_w = 6
    gap = 3
    bars = 12
    for i in range(bars):
        x0 = 6 + i * (bar_w + gap)
        # Deterministic rhythm pattern without randomness.
        pulse = ((frame_idx * (i + 3)) + i * 17) % 24
        h = 6 + pulse
        y0 = base_y - h
        draw.rectangle([x0, y0, x0 + bar_w, base_y], fill=(255, 255, 255))

    # Flashing lightning accent.
    if frame_idx % 8 in (0, 1):
        bolt_x = 100
        draw.polygon(
            [
                (bolt_x, 12),
                (bolt_x - 4, 24),
                (bolt_x + 1, 24),
                (bolt_x - 5, 38),
                (bolt_x + 8, 22),
                (bolt_x + 2, 22),
            ],
            fill=(255, 255, 255),
        )

    # Scrolling ROCK title for movement and readability in mono.
    text = "ROCK ON"
    text_w = len(text) * 8
    tx = WIDTH - ((frame_idx * 4) % (WIDTH + text_w))
    ty = 28
    draw.text((tx, ty), text, fill=(255, 255, 255))

    # Big center hit every beat.
    if frame_idx % 10 == 0:
        draw.text((42, 14), "HARD", fill=(255, 255, 255))

    frames.append(img)

if frames:
    frames[0].save(
        FILENAME,
        save_all=True,
        append_images=frames[1:],
        duration=60,
        loop=0,
        optimize=False,
    )
    print(f"Created: {FILENAME}")
    print(f"Frames: {len(frames)}")
    print(f"Size: {WIDTH}x{HEIGHT}")
    print(f"File size: {os.path.getsize(FILENAME)} bytes")
else:
    print("No frames generated")
