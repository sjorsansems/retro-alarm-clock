#!/usr/bin/env python3
"""
convert_upload.py  –  GIF → .bin converteren + direct uploaden naar ESP32 alarmklok
=====================================================================================
Voert gif_to_frames.py uit op de gekozen GIF en stuurt het resulterende .bin bestand
naar de klok via de v5 web-API.

Gebruik (vanuit de project-root):
    pip install Pillow requests
    python tools/convert_upload.py mijn_animatie.gif --ip 192.168.1.x

Opties:
    --ip     IP-adres van de ESP32 (default: 192.168.4.1)
    --port   Poort van de webserver (default: 80)
    --name   Naam voor het .bin bestand (default: bestandsnaam van de GIF)
    --thr    Wit/zwart drempel 0-255 (default: 128)
    --inv    Inverteer kleuren
    --dither Floyd-Steinberg dithering
    --max    Maximaal N frames (default: 200)
    --dry    Alleen converteren, niet uploaden (slaat .bin op in tools/)
"""

import sys
import os
import argparse

# Zorg dat tools/ gevonden wordt voor gif_to_frames import
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TOOLS_DIR)

try:
    from gif_to_frames import extract_gif_frames, write_output_bin
except ImportError as _e:
    print(f"Kan gif_to_frames niet importeren: {_e}")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("requests niet gevonden. Installeer met:  pip install requests")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="GIF converteren naar .bin en uploaden naar de alarmklok"
    )
    parser.add_argument("gif", help="Pad naar het GIF-bestand")
    parser.add_argument("--ip",     default="192.168.4.1", help="IP-adres van de ESP32 (default: 192.168.4.1)")
    parser.add_argument("--port",   type=int, default=80,  help="Webserver poort (default: 80)")
    parser.add_argument("--name",   default=None,          help="Naam voor het .bin bestand (zonder extensie)")
    parser.add_argument("--thr",    type=int, default=128, help="Drempel 0-255 (default: 128)")
    parser.add_argument("--inv",    action="store_true",   help="Inverteer kleuren")
    parser.add_argument("--dither", action="store_true",   help="Floyd-Steinberg dithering")
    parser.add_argument("--max",    type=int, default=200, help="Max frames (default: 200)")
    parser.add_argument("--dry",    action="store_true",   help="Alleen converteren, niet uploaden")
    args = parser.parse_args()

    if not os.path.isfile(args.gif):
        print(f"GIF niet gevonden: {args.gif}")
        sys.exit(1)

    # Bestandsnaam bepalen
    name = args.name or os.path.splitext(os.path.basename(args.gif))[0]
    # Sanitize: alleen alfanumeriek + - _
    safe_name = "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_"))[:32]
    if not safe_name:
        print(f"Ongeldige naam: '{name}'")
        sys.exit(1)

    bin_path = os.path.join(_TOOLS_DIR, safe_name + ".bin")

    # ── Stap 1: converteren ──────────────────────────────────────────────────
    print(f"\n[1/2] Converteren: {args.gif}  →  {bin_path}")
    frames, delays = extract_gif_frames(
        args.gif, 128, 64, args.thr, args.inv, args.dither
    )
    total = len(frames)
    print(f"  {total} frames gevonden")

    if total > args.max:
        print(f"  ✂ Afgekapt tot {args.max} frames")
        frames = frames[:args.max]
        delays = delays[:args.max]

    write_output_bin(frames, delays, 128, 64, bin_path)
    size = os.path.getsize(bin_path)
    print(f"  Geschreven: {bin_path}  ({size // 1024} KB)")

    if args.dry:
        print("\n--dry opgegeven: uploaden overgeslagen.")
        return

    # ── Stap 2: uploaden ─────────────────────────────────────────────────────
    url = f"http://{args.ip}:{args.port}/api/upload-bin?name={safe_name}"
    print(f"\n[2/2] Uploaden naar {url}")
    try:
        with open(bin_path, "rb") as f:
            data = f.read()
        resp = requests.post(
            url,
            data=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=30,
        )
        result = resp.json()
        if result.get("ok"):
            print(f"  ✓ Opgeslagen als {result.get('name')}  ({result.get('bytes')} bytes)")
            print(f"\nKlaar! Animatie '{safe_name}' is beschikbaar in de webinterface.")
        else:
            print(f"  ✗ Fout van klok: {result.get('error', 'onbekend')}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"  ✗ Kan ESP32 niet bereiken op {args.ip}:{args.port}")
        print("     Controleer of de klok aan staat en verbonden is met WiFi.")
        sys.exit(1)
    except Exception as e:
        print(f"  ✗ Upload fout: {e}")
        sys.exit(1)
    finally:
        # Verwijder tijdelijk .bin bestand
        try:
            os.remove(bin_path)
        except Exception:
            pass


if __name__ == "__main__":
    main()
