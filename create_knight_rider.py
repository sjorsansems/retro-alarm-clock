#!/usr/bin/env python3
"""
Generate Knight Rider KITT scanner animation GIF.
The iconic red scanning bar moving left-right across black background.
"""
from PIL import Image, ImageDraw
import os

# Configuration
WIDTH = 128  # OLED width
HEIGHT = 64  # OLED height
FRAMES = 32
FILENAME = "knight_rider.gif"

# Scanner bar properties
BAR_HEIGHT = 12
BAR_WIDTH = 20
SCANNER_COLOR = (255, 0, 0)  # Red
GLOW_COLOR = (100, 0, 0)  # Dim red

frames = []

# Generate frames: scanner moving left-to-right and back
for frame_idx in range(FRAMES):
    # Create black background
    img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Calculate scanner position (bounces left-right)
    # Half frames go left-to-right, half go right-to-left
    progress = (frame_idx % FRAMES) / FRAMES
    
    if frame_idx < FRAMES // 2:
        # Moving right
        progress = frame_idx / (FRAMES // 2)
        scanner_x = int(progress * (WIDTH - BAR_WIDTH))
    else:
        # Moving left
        progress = (frame_idx - FRAMES // 2) / (FRAMES // 2)
        scanner_x = int((1.0 - progress) * (WIDTH - BAR_WIDTH))
    
    # Draw glow (thicker, dimmer bar)
    glow_thickness = 16
    y_center = HEIGHT // 2
    draw.rectangle(
        [scanner_x - 2, y_center - glow_thickness // 2,
         scanner_x + BAR_WIDTH + 2, y_center + glow_thickness // 2],
        fill=GLOW_COLOR
    )
    
    # Draw main scanner bar (bright red, narrower)
    draw.rectangle(
        [scanner_x, y_center - BAR_HEIGHT // 2,
         scanner_x + BAR_WIDTH, y_center + BAR_HEIGHT // 2],
        fill=SCANNER_COLOR
    )
    
    # Draw horizontal line trace (faint scanner line)
    draw.line(
        [(0, y_center), (WIDTH, y_center)],
        fill=(50, 0, 0),
        width=1
    )
    
    # Add some corner accents (retro style)
    corner_size = 3
    draw.rectangle([1, 1, corner_size, corner_size], fill=(100, 0, 0))  # Top-left
    draw.rectangle([WIDTH - corner_size, 1, WIDTH - 1, corner_size], fill=(100, 0, 0))  # Top-right
    draw.rectangle([1, HEIGHT - corner_size, corner_size, HEIGHT - 1], fill=(100, 0, 0))  # Bottom-left
    draw.rectangle([WIDTH - corner_size, HEIGHT - corner_size, WIDTH - 1, HEIGHT - 1], fill=(100, 0, 0))  # Bottom-right
    
    frames.append(img)

# Save as GIF with animation
if frames:
    frames[0].save(
        FILENAME,
        save_all=True,
        append_images=frames[1:],
        duration=50,  # 50ms per frame = smooth animation
        loop=0,  # Infinite loop
        optimize=False
    )
    print(f"✓ Knight Rider GIF created: {FILENAME}")
    print(f"  Frames: {len(frames)}")
    print(f"  Size: {WIDTH}x{HEIGHT}")
    print(f"  File size: {os.path.getsize(FILENAME)} bytes")
else:
    print("! No frames generated")
