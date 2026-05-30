#!/usr/bin/env python3
"""
Generate a DOS-style retro animation GIF for the OLED clock.

The loop intentionally looks a bit broken: boot text, C:\> prompts,
fake virus warnings, and memory/setup errors in a playful retro way.
"""

from PIL import Image, ImageDraw, ImageFont
import os

WIDTH = 128
HEIGHT = 64
FRAMES = 40
OUTPUT = os.path.join("animations", "dos_meltdown.gif")

FONT = ImageFont.load_default()


def centered_text(draw, text, y, fill):
    bbox = draw.textbbox((0, 0), text, font=FONT)
    x = max(0, (WIDTH - (bbox[2] - bbox[0])) // 2)
    draw.text((x, y), text, font=FONT, fill=fill)


def draw_terminal(draw, lines, cursor_on=True, warning=False, footer=None):
    bg = (0, 0, 0)
    fg = (80, 255, 80) if not warning else (255, 80, 80)
    dim = (0, 120, 0) if not warning else (120, 0, 0)

    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=fg)
    # Subtle scanlines and a tiny bit of noise.
    for y in range(2, HEIGHT - 2, 4):
        draw.line((2, y, WIDTH - 3, y), fill=dim)

    for i in range(18):
        x = (i * 17) % WIDTH
        y = (i * 11 + 7) % HEIGHT
        draw.point((x, y), fill=fg)

    centered_text(draw, "RETRO BIOS 6.66", 2, fg)
    centered_text(draw, "C:\\>" if not warning else "A:\\>", 14, fg)

    yy = 26
    for line in lines:
        draw.text((8, yy), line, font=FONT, fill=fg)
        yy += 9

    if cursor_on:
        # Flikkerende cursor op de huidige promptregel.
        draw.rectangle((32, 15, 36, 20), fill=fg)

    if footer:
        centered_text(draw, footer, HEIGHT - 10, fg)


def scene_for_frame(frame_idx):
    phase = frame_idx // 8
    blink = frame_idx % 2 == 0

    if phase == 0:
        lines = [
            "Loading retro_mode.sys",
            "Checking memory...",
            "Drive C: OK",
        ]
        footer = "Press any key to continue"
        return lines, blink, False, footer

    if phase == 1:
        lines = [
            "Virus detected in C:\\CLOCK.SYS",
            "Quarantine failed",
            "Continue anyway? [Y/N]",
        ]
        footer = "Press Y to risk it"
        return lines, blink, True, footer

    if phase == 2:
        lines = [
            "Setup cannot install MS-DOS 6.22",
            "on your computer.",
            "Press F3 to reboot",
        ]
        footer = "Error 019: floppy not amused"
        return lines, blink, True, footer

    if phase == 3:
        lines = [
            "Not enough memory to run",
            "Wolvenstein 3-D.",
            "Try closing some TSRs.",
        ]
        footer = "HIMEM.SYS not responding"
        return lines, blink, True, footer

    if phase == 4:
        lines = [
            "C:\\> dir",
            "A:\\  ERROR",
            "B:\\  ERROR",
            "C:\\  READY?",
        ]
        footer = "SYSTEM HALTED - just kidding"
        return lines, blink, False, footer

    # Final phase: prompt loop.
    typing = "dir /w"
    typed = typing[:max(0, frame_idx - 32)]
    lines = [
        f"C:\\>{typed}",
        "Type HELP for more chaos",
        "Keyboard: [OK]  Mouse: [??]",
    ]
    footer = "C:\\>_" if blink else "C:\\>"
    return lines, blink, False, footer


def main():
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    frames = []

    for frame_idx in range(FRAMES):
        img = Image.new("RGB", (WIDTH, HEIGHT), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        lines, cursor_on, warning, footer = scene_for_frame(frame_idx)
        draw_terminal(draw, lines, cursor_on=cursor_on, warning=warning, footer=footer)

        # Little flicker every few frames.
        if frame_idx % 5 == 0:
            draw.rectangle((0, 0, WIDTH - 1, 1), fill=(40, 40, 40))
            draw.rectangle((0, HEIGHT - 2, WIDTH - 1, HEIGHT - 1), fill=(40, 40, 40))

        frames.append(img)

    if not frames:
        print("No frames generated")
        return

    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=90,
        loop=0,
        optimize=False,
    )

    print(f"Created: {OUTPUT}")
    print(f"Frames: {len(frames)}")
    print(f"Size: {WIDTH}x{HEIGHT}")
    print(f"File size: {os.path.getsize(OUTPUT)} bytes")


if __name__ == "__main__":
    main()