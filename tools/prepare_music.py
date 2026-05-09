#!/usr/bin/env python3
"""
prepare_music.py - Voorbereiding van MP3-nummers voor DFPlayer

Functionaliteit:
- Hernoem muziekbestanden naar 1.mp3, 2.mp3, ..., 9.mp3
- Converteer bitrate naar 128kbps (minder space op SD)
- Controleer bestandsduur
- Kopie naar deployment-map

Gebruik:
    python tools/prepare_music.py --input-dir ./downloads --output-dir ./music

Vereisten:
    pip install pydub
    (ffmpeg moet geïnstalleerd zijn: https://ffmpeg.org/download.html)
"""

import os
import sys
import argparse
import shutil
from pathlib import Path

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False
    print("⚠️  pydub niet gevonden. Installeer met: pip install pydub")
    print("   (ffmpeg moet ook geïnstalleerd zijn)")


TRACK_INFO = {
    1: {"name": "Zelda", "theme": "Fantasy/Adventure"},
    2: {"name": "Mario", "theme": "Retro Game"},
    3: {"name": "Synthwave", "theme": "Neon/80s Synth"},
    4: {"name": "Sonic", "theme": "Fast/Upbeat"},
    5: {"name": "Metroid", "theme": "Sci-Fi/Space"},
    6: {"name": "Pokemon", "theme": "Kawaii/Playful"},
    7: {"name": "Tetris", "theme": "Retro/Energetic"},
    8: {"name": "Moonstone", "theme": "Dark/Epic"},
    9: {"name": "Arcade", "theme": "Fast/Action"},
}


def find_audio_files(directory):
    """Zoek alle MP3/WAV/M4A bestanden in directory."""
    path = Path(directory)
    if not path.exists():
        print(f"❌ Map niet gevonden: {directory}")
        return []
    
    audio_exts = {'.mp3', '.wav', '.m4a', '.flac', '.ogg'}
    files = sorted([
        f for f in path.iterdir()
        if f.is_file() and f.suffix.lower() in audio_exts
    ])
    return files


def get_audio_duration(filepath):
    """Haal duur van audiobestand op (in seconden)."""
    if not HAS_PYDUB:
        return None
    try:
        audio = AudioSegment.from_file(str(filepath))
        return len(audio) / 1000.0  # ms naar seconden
    except Exception as e:
        print(f"  ⚠️  Duur kon niet bepaald worden: {e}")
        return None


def convert_to_mp3(input_file, output_file, bitrate="128k"):
    """Converteer audiobestand naar MP3 met lagere bitrate."""
    if not HAS_PYDUB:
        print(f"  ℹ️  pydub niet beschikbaar; file wordt overgeslagen")
        return False
    
    try:
        print(f"  🔄 Converteer naar MP3 ({bitrate})...")
        audio = AudioSegment.from_file(str(input_file))
        audio.export(str(output_file), format="mp3", bitrate=bitrate)
        print(f"  ✅ Geconverteerd naar {output_file}")
        return True
    except Exception as e:
        print(f"  ❌ Conversie fout: {e}")
        return False


def prepare_music_interactive(input_dir, output_dir, zero_pad=False):
    """Interactief: kies bestanden voor elk track.
    
    Args:
        zero_pad: Maak bestanden aan als 0001.mp3-0009.mp3 i.p.v. 1.mp3-9.mp3
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    files = find_audio_files(input_dir)
    if not files:
        print(f"❌ Geen audiobestanden gevonden in {input_dir}")
        return False
    
    print(f"\n✅ {len(files)} audiobestanden gevonden:\n")
    for i, f in enumerate(files, 1):
        dur = get_audio_duration(f)
        dur_str = f"{dur:.1f}s" if dur else "?"
        print(f"  [{i}] {f.name} ({dur_str})")
    
    assigned = {}
    for track_num in range(1, 10):
        info = TRACK_INFO[track_num]
        print(f"\n🎵 Track {track_num}: {info['name']} ({info['theme']})")
        
        choice = input(f"Kies bestand [1-{len(files)}] (skip=enter): ").strip()
        if not choice:
            print(f"  ⏭️  Overgeslagen")
            continue
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                assigned[track_num] = files[idx]
                print(f"  ✅ Toegewezen: {files[idx].name}")
            else:
                print(f"  ❌ Ongeldig nummer")
        except ValueError:
            print(f"  ❌ Geen geldig getal")
    
    if not assigned:
        print("\n❌ Geen bestanden toegewezen")
        return False
    
    # Verwerk toegewezen bestanden
    print(f"\n📁 Voorbereiding naar {output_dir}...\n")
    for track_num, src_file in assigned.items():
        if zero_pad:
            out_filename = f"{track_num:04d}.mp3"  # 0001.mp3, 0002.mp3, ...
        else:
            out_filename = f"{track_num}.mp3"     # 1.mp3, 2.mp3, ...
        out_file = output_path / out_filename
        print(f"Track {track_num}:")
        
        if src_file.suffix.lower() == '.mp3':
            # Reeds MP3: kopie
            print(f"  📋 Kopie {src_file.name} → {out_file.name}")
            shutil.copy2(src_file, out_file)
        else:
            # Converteer
            print(f"  🔄 Converteer {src_file.name} → {out_file.name}")
            if HAS_PYDUB:
                convert_to_mp3(src_file, out_file)
            else:
                shutil.copy2(src_file, out_file)
        
        dur = get_audio_duration(out_file)
        if dur:
            print(f"  ⏱️  Duur: {dur:.1f}s")
    
    print(f"\n✅ Klaar! Bestanden in: {output_dir}")
    print(f"\n💡 Volgende stap: Kopie naar ESP32:")
    print(f"   python -m mpremote connect COM7 \\")
    for i in range(1, 10):
        if (output_path / f"{i}.mp3").exists():
            print(f"     cp {output_dir}/{i}.mp3 :{i}.mp3 + \\")
    print(f"     reset")
    
    return True


def prepare_music_batch(input_dir, output_dir, convert_bitrate=None, zero_pad=False):
    """Batch: alle bestanden automatisch in volgorde.
    
    Args:
        zero_pad: Maak bestanden aan als 0001.mp3-0009.mp3 i.p.v. 1.mp3-9.mp3
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    files = find_audio_files(input_dir)
    if not files:
        print(f"❌ Geen audiobestanden gevonden in {input_dir}")
        return False
    
    print(f"✅ {len(files)} bestanden gevonden\n")
    
    for track_num, src_file in enumerate(files[:9], 1):
        if zero_pad:
            out_filename = f"{track_num:04d}.mp3"  # 0001.mp3, 0002.mp3, ...
        else:
            out_filename = f"{track_num}.mp3"     # 1.mp3, 2.mp3, ...
        out_file = output_path / out_filename
        info = TRACK_INFO[track_num]
        
        print(f"Track {track_num} ({info['name']}):")
        print(f"  📝 Bron: {src_file.name}")
        
        if src_file.suffix.lower() == '.mp3' and not convert_bitrate:
            print(f"  📋 Kopie naar {out_file.name}")
            shutil.copy2(src_file, out_file)
        elif convert_bitrate or src_file.suffix.lower() != '.mp3':
            br = convert_bitrate or "128k"
            print(f"  🔄 Converteer naar MP3 ({br})")
            if HAS_PYDUB:
                convert_to_mp3(src_file, out_file, bitrate=br)
            else:
                shutil.copy2(src_file, out_file)
        
        dur = get_audio_duration(out_file)
        if dur:
            print(f"  ⏱️  Duur: {dur:.1f}s")
        print()
    
    print(f"✅ Klaar! {len(files)} bestanden verwerkt in: {output_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Voorbereiding MP3-nummers voor DFPlayer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Voorbeelden:
  # Interactief: kies welk bestand voor welk track
  python tools/prepare_music.py --input-dir ./downloads --output-dir ./music

  # Batch: eerste 9 bestanden in volgorde
  python tools/prepare_music.py --batch --input-dir ./downloads --output-dir ./music

  # Met bitrate-conversie
  python tools/prepare_music.py --batch --convert-bitrate 96k --input-dir ./downloads --output-dir ./music
        """
    )
    parser.add_argument("--input-dir", default="./downloads", help="Map met audiobestanden")
    parser.add_argument("--output-dir", default="./music", help="Uitvoer-map voor 1.mp3-9.mp3 (of 0001-0009.mp3)")
    parser.add_argument("--batch", action="store_true", help="Batch modus (auto, geen interactie)")
    parser.add_argument("--zero-pad", action="store_true", help="Maak zero-padded bestandsnamen (0001.mp3-0009.mp3)")
    parser.add_argument("--convert-bitrate", default=None, help="Converteer naar bitrate (bijv. 96k, 128k)")
    
    args = parser.parse_args()
    
    print("🎵 Alarmklok MP3 Voorbereiding\n")
    
    if args.batch:
        success = prepare_music_batch(args.input_dir, args.output_dir, args.convert_bitrate, args.zero_pad)
    else:
        success = prepare_music_interactive(args.input_dir, args.output_dir, args.zero_pad)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
