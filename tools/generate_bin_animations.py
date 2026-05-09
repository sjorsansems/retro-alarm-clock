#!/usr/bin/env python3
"""
generate_bin_animations.py
Genereert 10 retro 1-bit .bin animaties voor 128x64 OLED wekker.
Elke animatie is een perfect 1-bit loop, geen externe GIFs nodig.

Gebruik (vanuit de project-root):
    pip install Pillow
    python tools/generate_bin_animations.py

Animaties:
    pacman.bin     Pac-Man eet dots, ghost volgt
    pong.bin       Classic Pong met AI paddles
    heartbeat.bin  ECG hartslag "WAKE UP!"
    fire.bin       Pixel vuur (cellular automaton)
    skull.bin      Grote schedel met knipperende ogen + bewegende kaak
    ufo.bin        UFO met tractor beam die koe ophijst
    space.bin      Space shooter met aliens en lasers
    radar.bin      Draaiende radar sweep met blips
    snake.bin      Snake spel
    matrix.bin     The Matrix vallende tekens
"""
from PIL import Image, ImageDraw
import struct, os, math, random

W, H = 128, 64
FRAME_SIZE = W * H // 8  # 1024 bytes per frame

random.seed(42)  # reproduceerbaar


# ─── Core conversie ──────────────────────────────────────────────────────────

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


def write_bin(name: str, frames: list, delays: list) -> None:
    n = len(frames)
    path = f"{name}.bin"
    with open(path, "wb") as f:
        f.write(bytes([0x47, 0xAF]))
        f.write(struct.pack(">H", n))
        f.write(bytes([W, H]))
        for d in delays:
            f.write(struct.pack(">H", d))
        for fr in frames:
            f.write(fr)
    kb = os.path.getsize(path) / 1024
    print(f"  {name}.bin  {n} frames  {kb:.1f}KB")


def blank() -> Image.Image:
    return Image.new("L", (W, H), 0)


# ─── 1. PAC-MAN ──────────────────────────────────────────────────────────────

def gen_pacman():
    frames, delays = [], []
    PAC_Y = 34
    DOT_SPACING = 14
    dots_x = list(range(14, 128, DOT_SPACING))

    for f in range(20):
        img = blank()
        d = ImageDraw.Draw(img)

        pac_x = (f * 5) % 128

        # Dots (nog niet opgegeten)
        for dx in dots_x:
            if (dx - pac_x) % 128 > 8:
                d.ellipse([dx - 3, PAC_Y - 3, dx + 3, PAC_Y + 3], fill=255)

        # Pac-Man
        mouth_deg = abs((f % 8) - 4) * 12   # 0..48 graden
        d.pieslice([pac_x - 10, PAC_Y - 10, pac_x + 10, PAC_Y + 10],
                   start=mouth_deg, end=360 - mouth_deg, fill=255)

        # Ghost (30px achter)
        gx = pac_x - 32
        if gx < 0:
            gx += 128
        gy = PAC_Y
        # Lichaam
        d.ellipse([gx - 9, gy - 10, gx + 9, gy + 2], fill=255)
        d.rectangle([gx - 9, gy - 3, gx + 9, gy + 9], fill=255)
        # Wiggly onderkant
        for wi in range(3):
            wx = gx - 8 + wi * 6
            d.ellipse([wx, gy + 5, wx + 5, gy + 12], fill=0)
        # Ogen
        d.ellipse([gx - 6, gy - 7, gx - 2, gy - 2], fill=0)
        d.ellipse([gx + 2, gy - 7, gx + 6, gy - 2], fill=0)
        d.point((gx - 5, gy - 6), fill=255)
        d.point((gx + 3, gy - 6), fill=255)

        # Vloer
        d.line([(0, PAC_Y + 14), (128, PAC_Y + 14)], fill=255)
        # Score
        d.text((4, 2), "PAC-MAN", fill=255)
        score = (f * 200) % 9999
        d.text((4, 54), str(score).rjust(5), fill=255)
        d.text((86, 2), "ALARM!", fill=255)

        frames.append(img_to_vlsb(img))
        delays.append(80)

    write_bin("pacman", frames, delays)


# ─── 2. PONG ─────────────────────────────────────────────────────────────────

def gen_pong():
    frames, delays = [], []
    bx, by = 64.0, 32.0
    vx, vy = 3.2, 2.1
    p1y, p2y = 24.0, 24.0
    PH = 14
    score1 = score2 = 0

    for f in range(32):
        img = blank()
        d = ImageDraw.Draw(img)

        # Middenlijn stippels
        for y in range(4, H, 8):
            d.line([(64, y), (64, y + 4)], fill=255)

        # Score
        d.text((44, 2), str(score1), fill=255)
        d.text((76, 2), str(score2), fill=255)

        # Paddles
        d.rectangle([4, int(p1y), 8, int(p1y) + PH], fill=255)
        d.rectangle([120, int(p2y), 124, int(p2y) + PH], fill=255)

        # Bal
        d.rectangle([int(bx) - 2, int(by) - 2, int(bx) + 2, int(by) + 2], fill=255)

        frames.append(img_to_vlsb(img))
        delays.append(50)

        # Physics
        bx += vx;  by += vy
        if by < 3:   by = 3;   vy = abs(vy)
        if by > H-3: by = H-3; vy = -abs(vy)

        # AI paddles
        mid1 = p1y + PH / 2;  mid2 = p2y + PH / 2
        if by > mid1 + 3: p1y = min(H - PH, p1y + 2.2)
        elif by < mid1 - 3: p1y = max(0, p1y - 2.2)
        if by > mid2 + 3: p2y = min(H - PH, p2y + 2.2)
        elif by < mid2 - 3: p2y = max(0, p2y - 2.2)

        # Paddle bounces
        if bx < 14 and p1y < by < p1y + PH:
            bx = 14; vx = abs(vx) * 1.05
            vy += (by - (p1y + PH/2)) * 0.1
        if bx > 114 and p2y < by < p2y + PH:
            bx = 114; vx = -abs(vx) * 1.05
            vy += (by - (p2y + PH/2)) * 0.1

        # Score / reset
        if bx < 0:   bx = 64; by = 32; vx = 3.2; vy = 2.1; score2 += 1
        if bx > 128: bx = 64; by = 32; vx = -3.2; vy = 2.1; score1 += 1

    write_bin("pong", frames, delays)


# ─── 3. HEARTBEAT (ECG) ──────────────────────────────────────────────────────

def gen_heartbeat():
    frames, delays = [], []

    # ECG patroon: plat, P-golf, QRS-complex, T-golf
    ecg_pat = [0]*6 + [3, 5, 3] + [0]*4 + [4, -10, 30, -12, 6, 0] + [0]*3 + [4, 6, 4] + [0]*8

    # Herhaal zodat er genoeg is
    ecg_long = ecg_pat * 8

    CY = 40
    SCALE = 1.2

    for f in range(28):
        img = blank()
        d = ImageDraw.Draw(img)

        # Grid
        for gy in range(14, H - 4, 10):
            for gx in range(0, W, 6):
                d.point((gx, gy), fill=200)  # punt -> wit op OLED

        # ECG lijn
        offset = f * 3
        prev_y = None
        for x in range(2, W - 2):
            idx = (x + offset) % len(ecg_long)
            y = int(CY - ecg_long[idx] * SCALE)
            y = max(12, min(H - 6, y))
            if prev_y is not None:
                d.line([(x - 1, prev_y), (x, y)], fill=255)
            prev_y = y

        # Pulsbol rechts
        pulse = (f // 4) % 2
        if pulse == 0:
            d.ellipse([110, 2, 124, 12], fill=255)
        else:
            d.ellipse([110, 2, 124, 12], outline=255)

        # BPM
        bpm = 68 + (f % 4) * 3
        d.text((2, 2), f"BPM {bpm}", fill=255)

        # Alarm balk
        if (f // 7) % 2 == 0:
            d.rectangle([0, 56, 128, 64], fill=255)
            d.text((40, 57), "ALARM!", fill=0)
        else:
            d.text((40, 57), "ALARM!", fill=255)

        frames.append(img_to_vlsb(img))
        delays.append(55)

    write_bin("heartbeat", frames, delays)


# ─── 4. FIRE ─────────────────────────────────────────────────────────────────

def gen_fire():
    random.seed(99)
    grid = [[0] * W for _ in range(H)]
    frames, delays = [], []

    for f in range(28):
        # Stook de bodem op
        for x in range(W):
            grid[H - 1][x] = 255 if random.random() > 0.15 else random.randint(80, 200)
            grid[H - 2][x] = 220 if random.random() > 0.2 else 120

        # Propageer omhoog
        for y in range(H - 3, -1, -1):
            for x in range(W):
                left  = grid[y + 1][max(0, x - 1)]
                mid   = grid[y + 1][x]
                right = grid[y + 1][min(W - 1, x + 1)]
                avg = (left + mid + right + mid) // 4
                grid[y][x] = max(0, avg - random.randint(6, 18))

        img = blank()
        d = ImageDraw.Draw(img)

        for y in range(H):
            for x in range(W):
                if grid[y][x] > 80:
                    d.point((x, y), fill=255)

        # Vuur tekst bovenin
        d.text((4, 2), "FIRE ALARM", fill=255)

        frames.append(img_to_vlsb(img))
        delays.append(55)

    write_bin("fire", frames, delays)


# ─── 5. SKULL ────────────────────────────────────────────────────────────────

def gen_skull():
    frames, delays = [], []

    for f in range(20):
        img = blank()
        d = ImageDraw.Draw(img)

        # Hoofd
        d.ellipse([16, 2, 112, 54], fill=255)

        # Ogen
        blink = (f % 7 == 0)
        if not blink:
            d.ellipse([30, 14, 52, 36], fill=0)
            d.ellipse([76, 14, 98, 36], fill=0)
            # Pupillen
            d.ellipse([37, 20, 46, 29], fill=255)
            d.ellipse([83, 20, 92, 29], fill=255)
            d.point((40, 23), fill=0)
            d.point((86, 23), fill=0)
        else:
            d.line([(30, 25), (52, 25)], fill=0, width=3)
            d.line([(76, 25), (98, 25)], fill=0, width=3)

        # Neus driehoek
        d.polygon([(64, 32), (56, 46), (72, 46)], fill=0)

        # Kaak (beweegt)
        jaw_open = (f % 5) * 2
        jaw_y = 48 + jaw_open
        d.rectangle([26, 48, 102, jaw_y + 10], fill=255)
        # Tanden
        for ti in range(5):
            tx = 28 + ti * 14
            d.rectangle([tx, 50, tx + 10, jaw_y + 6], fill=0)

        # Romige schedule
        d.rectangle([0, 56, 128, 64], fill=0)
        if (f // 5) % 2 == 0:
            d.text((38, 57), "WAKE UP!!", fill=255)

        frames.append(img_to_vlsb(img))
        delays.append(100)

    write_bin("skull", frames, delays)


# ─── 6. UFO ──────────────────────────────────────────────────────────────────

def gen_ufo():
    frames, delays = [], []

    for f in range(24):
        img = blank()
        d = ImageDraw.Draw(img)

        # Achtergrond sterren
        for i in range(18):
            sx = (i * 19 + f * (1 + i % 2)) % W
            sy = 2 + (i * 9 % 24)
            d.point((sx, sy), fill=255)

        # UFO positie (zijwaarts heen en weer)
        ux = 40 + int(28 * math.sin(f * 0.28))
        uy = 4

        # Koepel
        d.ellipse([ux + 8, uy - 2, ux + 28, uy + 8], fill=255)
        d.ellipse([ux + 12, uy + 1, ux + 24, uy + 6], fill=0)

        # Romp
        d.ellipse([ux, uy + 6, ux + 36, uy + 16], fill=255)
        d.ellipse([ux + 2, uy + 8, ux + 34, uy + 14], fill=0)

        # Porthole
        d.ellipse([ux + 14, uy + 8, ux + 22, uy + 14], fill=255)

        # Lampjes
        for li in range(4):
            lx = ux + 3 + li * 9
            if (f + li) % 3 == 0:
                d.point((lx, uy + 16), fill=255)
                d.point((lx + 1, uy + 16), fill=255)

        # Tractor beam
        beam_cx = ux + 18
        beam_w = 6 + (f % 8) * 1
        beam_bot = 52
        d.polygon([
            (beam_cx, uy + 16),
            (beam_cx - beam_w, beam_bot),
            (beam_cx + beam_w, beam_bot),
        ], outline=255)
        # Beam strepen
        for bi in range(4):
            by2 = uy + 20 + bi * 8
            bw2 = (bi + 1) * beam_w // 5
            d.line([(beam_cx - bw2, by2), (beam_cx + bw2, by2)], fill=255)

        # Koe
        cow_y = 50 - (f % 12) * 2
        cow_y = max(18, cow_y)
        cx2 = beam_cx - 10
        cy2 = cow_y
        # Lichaam
        d.ellipse([cx2, cy2 + 2, cx2 + 18, cy2 + 10], fill=255)
        # Hoofd
        d.ellipse([cx2 + 12, cy2 - 2, cx2 + 22, cy2 + 6], fill=255)
        # Oor + oog
        d.point((cx2 + 20, cy2 - 1), fill=255)
        d.point((cx2 + 18, cy2 + 1), fill=0)
        # Poten
        for pi in range(4):
            px2 = cx2 + 2 + pi * 4
            d.line([(px2, cy2 + 10), (px2, cy2 + 16)], fill=255)
        # Staart
        d.line([(cx2, cy2 + 4), (cx2 - 4, cy2)], fill=255)

        # Grond
        d.line([(0, 58), (W, 58)], fill=255)

        # Alarm
        if (f // 6) % 2 == 0:
            d.rectangle([0, 56, 128, 64], fill=255)
            d.text((40, 57), "ALARM!", fill=0)
        else:
            d.text((40, 57), "ALARM!", fill=255)

        frames.append(img_to_vlsb(img))
        delays.append(80)

    write_bin("ufo", frames, delays)


# ─── 7. SPACE SHOOTER ────────────────────────────────────────────────────────

def gen_space():
    frames, delays = [], []
    random.seed(7)
    stars = [(random.randint(0, W-1), random.randint(0, H-1), random.randint(1, 3))
             for _ in range(35)]

    for f in range(28):
        img = blank()
        d = ImageDraw.Draw(img)

        # Scrollende sterren
        for i, (sx, sy, sp) in enumerate(stars):
            nx = (sx - sp) % W
            stars[i] = (nx, sy, sp)
            sz = 2 if sp == 3 else 1
            d.rectangle([nx, sy, nx + sz - 1, sy + sz - 1], fill=255)

        # Spelerschip (links, vliegt stabiel)
        sx2, sy2 = 18, 26
        # Romp
        d.polygon([
            (sx2 + 14, sy2 + 5),   # neus
            (sx2, sy2),            # boven links
            (sx2 + 4, sy2 + 4),    # inham boven
            (sx2, sy2 + 10),       # onder links
            (sx2 + 4, sy2 + 6),    # inham onder
            (sx2 + 14, sy2 + 5),
        ], fill=255)
        # Motor-gloed (pulsend)
        if f % 3 < 2:
            d.rectangle([sx2, sy2 + 3, sx2 + 3, sy2 + 7], fill=0)

        # Laser
        laser_frame = f % 6
        laser_x = sx2 + 14 + laser_frame * 14
        if laser_frame < 4:
            d.line([(sx2 + 14, sy2 + 5), (laser_x, sy2 + 5)], fill=255)
            d.point((laser_x, sy2 + 4), fill=255)
            d.point((laser_x, sy2 + 6), fill=255)

        # Vijanden (3 rijen van rechts naar links)
        for row in range(3):
            for col in range(4):
                ex = W - 10 - col * 22 + (f * 2) % 22
                ey = 6 + row * 14
                if 10 < ex < W:
                    # Alien schotel
                    d.ellipse([ex, ey, ex + 14, ey + 7], fill=255)
                    d.ellipse([ex + 4, ey - 3, ex + 10, ey + 3], fill=255)
                    d.ellipse([ex + 2, ey + 1, ex + 12, ey + 6], fill=0)
                    # Bom
                    if (f + row * 3 + col * 5) % 8 < 4:
                        bomb_y = ey + 8 + ((f * 2 + col * 7) % 16)
                        if bomb_y < H - 6:
                            d.line([(ex + 7, ey + 7), (ex + 7, bomb_y)], fill=255)

        # Grond
        d.line([(0, H - 4), (W, H - 4)], fill=255)
        # Score
        d.text((2, H - 12), f"SC:{(f*1337)%9999:04d}", fill=255)

        frames.append(img_to_vlsb(img))
        delays.append(55)

    write_bin("space", frames, delays)


# ─── 8. RADAR ────────────────────────────────────────────────────────────────

def gen_radar():
    frames, delays = [], []
    CX, CY, R = 40, 34, 30
    blips = [(CX - 12, CY - 8), (CX + 18, CY - 14), (CX + 8, CY + 16),
             (CX - 18, CY + 10), (CX + 22, CY + 8)]

    for f in range(28):
        img = blank()
        d = ImageDraw.Draw(img)

        # Cirkels
        for r in range(8, R + 2, 8):
            d.ellipse([CX - r, CY - r, CX + r, CY + r], outline=255)

        # Kruis
        d.line([(CX - R, CY), (CX + R, CY)], fill=255)
        d.line([(CX, CY - R), (CX, CY + R)], fill=255)

        # Sweep
        angle_deg = (f * 360 / 28) % 360
        angle_rad = math.radians(angle_deg)
        ex = CX + int(R * math.cos(angle_rad))
        ey = CY + int(R * math.sin(angle_rad))
        d.line([(CX, CY), (ex, ey)], fill=255)

        # Trail (3 voorgaande)
        for t in range(1, 4):
            trail_deg = angle_deg - t * 14
            trail_rad = math.radians(trail_deg)
            tr = R - t * 4
            tex = CX + int(tr * math.cos(trail_rad))
            tey = CY + int(tr * math.sin(trail_rad))
            d.line([(CX, CY), (tex, tey)], fill=255)

        # Blips
        for bx2, by2 in blips:
            b_angle = math.degrees(math.atan2(by2 - CY, bx2 - CX)) % 360
            diff = (angle_deg - b_angle) % 360
            if diff < 40:
                d.rectangle([bx2 - 2, by2 - 2, bx2 + 2, by2 + 2], fill=255)
            else:
                d.point((bx2, by2), fill=255)

        # Midpunt
        d.rectangle([CX - 1, CY - 1, CX + 1, CY + 1], fill=255)

        # Sidepanel
        d.text((82, 2), "RADAR", fill=255)
        d.line([(80, 12), (126, 12)], fill=255)
        d.text((82, 15), "OBJECTS", fill=255)
        d.text((82, 24), f"  {len(blips)}", fill=255)
        d.text((82, 36), "SWEEP", fill=255)
        deg_str = f"{int(angle_deg):3d}deg"
        d.text((82, 45), deg_str, fill=255)

        # Alarm
        if (f // 7) % 2 == 0:
            d.rectangle([80, 56, 128, 64], fill=255)
            d.text((82, 57), "ALARM!", fill=0)
        else:
            d.text((82, 57), "ALARM!", fill=255)

        frames.append(img_to_vlsb(img))
        delays.append(60)

    write_bin("radar", frames, delays)


# ─── 9. SNAKE ────────────────────────────────────────────────────────────────

def gen_snake():
    frames, delays = [], []
    CELL = 8
    COLS = W // CELL     # 16
    ROWS = (H - 14) // CELL  # 6

    # Pre-reken een lange slang-pad (spiraal)
    path = []
    for row in range(ROWS):
        if row % 2 == 0:
            for col in range(COLS):
                path.append((col, row))
        else:
            for col in range(COLS - 1, -1, -1):
                path.append((col, row))

    LEN = 10

    # Vaste appel positie (staat op pad)
    apple_path_idx = len(path) // 2
    apple_cell = path[apple_path_idx]

    for f in range(28):
        img = blank()
        d = ImageDraw.Draw(img)

        # Border
        d.rectangle([0, 14, W - 1, H - 1], outline=255)

        # Subtiel grid
        for gc in range(1, COLS):
            d.line([(gc * CELL, 15), (gc * CELL, H - 2)], fill=200)
        for gr in range(1, ROWS):
            d.line([(1, 14 + gr * CELL), (W - 2, 14 + gr * CELL)], fill=200)

        # Slang
        head_idx = (f * 1) % len(path)
        for i in range(LEN):
            idx = (head_idx - i) % len(path)
            cx2, cy2 = path[idx]
            px2 = cx2 * CELL + 1
            py2 = 14 + cy2 * CELL + 1
            if i == 0:
                # Hoofd
                d.rectangle([px2, py2, px2 + CELL - 3, py2 + CELL - 3], fill=255)
                # Ogen
                d.point((px2 + 1, py2 + 1), fill=0)
                d.point((px2 + 4, py2 + 1), fill=0)
            else:
                d.rectangle([px2 + 1, py2 + 1, px2 + CELL - 4, py2 + CELL - 4], fill=255)

        # Appel (knippert als slang dichtbij)
        ax2 = apple_cell[0] * CELL + 1
        ay2 = 14 + apple_cell[1] * CELL + 1
        if f % 4 < 3:
            d.ellipse([ax2 + 1, ay2 + 1, ax2 + CELL - 4, ay2 + CELL - 4], fill=255)
            d.line([(ax2 + 3, ay2), (ax2 + 3, ay2 - 2)], fill=255)  # steeltje

        # HUD
        d.text((2, 2), "SNAKE", fill=255)
        d.text((54, 2), f"LEN:{LEN + f // 10}", fill=255)

        frames.append(img_to_vlsb(img))
        delays.append(75)

    write_bin("snake", frames, delays)


# ─── 10. MATRIX ──────────────────────────────────────────────────────────────

def gen_matrix():
    random.seed(77)
    N_COLS = 21     # ~6px breed per kolom
    COL_W = 6

    # State per kolom: (y, speed)
    cols = [(random.randint(-H, 0), random.randint(1, 3)) for _ in range(N_COLS)]

    # Karakter patronen (5x7 pixels, gesimplificeerd als vaste bits)
    CHARS = [
        0b1010101, 0b1100011, 0b0110110, 0b1001001,
        0b1111000, 0b0001111, 0b1010010, 0b0101101,
    ]

    frames, delays = [], []

    for f in range(32):
        img = blank()
        d = ImageDraw.Draw(img)

        for ci in range(N_COLS):
            cy2, speed = cols[ci]
            cx2 = ci * COL_W

            # Trek spoor van lichtere karakters (trail)
            for ti in range(6):
                trail_y = cy2 - ti * 7
                if 0 <= trail_y < H - 6:
                    char_bits = CHARS[(ci + f + ti) % len(CHARS)]
                    if ti == 0:  # hoofd (helderst)
                        d.rectangle([cx2, trail_y, cx2 + 4, trail_y + 5], fill=255)
                        # Karakter inhoud (simpel patroon)
                        for bi in range(7):
                            if char_bits & (1 << bi):
                                row_bits = (bi * (ci + f)) % 5
                                for bx2 in range(5):
                                    if (bx2 + row_bits) % 2:
                                        d.point((cx2 + bx2, trail_y + bi % 5), fill=0)
                    else:
                        # Trail: afwisselende pixels
                        if ti < 3:
                            d.rectangle([cx2, trail_y, cx2 + 4, trail_y + 5], fill=255)
                            d.rectangle([cx2 + 1, trail_y + 1, cx2 + 3, trail_y + 4], fill=0)

            # Update positie
            cols[ci] = (cy2 + speed * 2, speed)
            if cy2 > H + 20:
                cols[ci] = (-random.randint(10, 40), random.randint(1, 3))

        # Titel
        d.rectangle([24, 0, 104, 12], fill=0)
        d.text((28, 2), "WAKE UP NEO", fill=255)

        frames.append(img_to_vlsb(img))
        delays.append(55)

    write_bin("matrix", frames, delays)


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Genereer 10 retro 1-bit .bin animaties voor 128x64 OLED...\n")
    gen_pacman()
    gen_pong()
    gen_heartbeat()
    gen_fire()
    gen_skull()
    gen_ufo()
    gen_space()
    gen_radar()
    gen_snake()
    gen_matrix()
    print("\nKlaar! Alle .bin bestanden staan in de huidige map.")
    print("\nDeploy naar ESP32:")
    names = ["pacman","pong","heartbeat","fire","skull","ufo","space","radar","snake","matrix"]
    cmd = "python -m mpremote connect COM7"
    for name in names:
        cmd += f" cp {name}.bin :{name}.bin +"
    cmd += " reset"
    print(f"  {cmd}")
