# 🎵 Alarmklok MP3-Nummers Setup Guide

Het DFPlayer Mini verwacht **9 MP3-bestanden** op de SD-kaart: `1.mp3` t/m `9.mp3`.

Elke track speelt af wanneer de gebruiker die tone kiest bij het alarm.

## 📋 Huidige Tone-Mapping

| Track | Naam | Thema | Animatie |
|-------|------|-------|----------|
| 1 | Zelda | Fantasy/Adventure | Mario/Zelda |
| 2 | Mario | Retro Game | Mario |
| 3 | Synthwave | Neon/80s Synth | Synthwave |
| 4 | Sonic | Fast/Upbeat | Sonic |
| 5 | Metroid | Sci-Fi/Space | Metroid |
| 6 | Pokemon | Kawaii/Playful | Pokemon |
| 7 | Tetris | Retro/Energetic | Tetris |
| 8 | Moonstone | Dark/Epic | Moonstone |
| 9 | Arcade | Fast/Action | Arcade (Space Invaders) |

## 🎶 Waar Muziek Vinden

### Optie 1: **Freepd.com** (Aanbevolen)
- 100% gratis, CC-licenties, geen account nodig
- Zoek op genre/stemming
- Download direct MP3

**Voor elk thema suggesties:**
- **Zelda** → "Adventure", "Fantasy", "8-bit"
- **Mario** → "Retro", "Game", "Cheerful"
- **Synthwave** → "Synthwave", "Neon", "80s"
- **Sonic** → "Upbeat", "Fast", "Energetic"
- **Metroid** → "Sci-Fi", "Space", "Dark"
- **Pokemon** → "Cute", "Playful", "Kawaii"
- **Tetris** → "Retro", "Puzzle", "Electronic"
- **Moonstone** → "Epic", "Dark", "Boss"
- **Arcade** → "Action", "Game", "Fast"

**Website:** https://freepd.com

### Optie 2: **Incompetech** (Muziek zonder Copyright)
- Veel retro/game-achtige tracks
- Creative Commons
- Download direct MP3

**Website:** https://incompetech.com/music/royalty-free/search.php?s=

### Optie 3: **YouTube Audio Library** (Gratis voor YouTube-gebruikers)
- Ingelogd in YouTube Studio → Audio-bibliotheek
- Filter op genre/stemming
- Download MP3 direct

### Optie 4: **itch.io Game Audio** (Open Game Assets)
- Veel Game Developers delen muziek
- Zoek op tag "music" + genre
- Controleer licentie (meestal CC0)

**Website:** https://itch.io/game-assets/music

## 📥 Voorbereiding

### Stap 1: Download 9 Nummers

Voor elk thema:
1. Ga naar één van bovenstaande sites
2. Zoek op het onderwerp
3. Download als **MP3, ~30-60 sec** (alarmtijd beperkt)
4. Rename naar `1.mp3`, `2.mp3`, etc.

**Voorbeeld directory:**
```
AlarmKlok/music/
  1.mp3    (Zelda)
  2.mp3    (Mario)
  3.mp3    (Synthwave)
  4.mp3    (Sonic)
  5.mp3    (Metroid)
  6.mp3    (Pokemon)
  7.mp3    (Tetris)
  8.mp3    (Moonstone)
  9.mp3    (Arcade)
```

### Stap 2: Converteer naar Bitrate (optioneel maar aanbevolen)

Als je files groot zijn, converteer naar 128kbps of 96kbps met **FFmpeg**:

```bash
ffmpeg -i 1.mp3 -b:a 128k 1_converted.mp3
mv 1_converted.mp3 1.mp3
```

Dit bespaart flash-ruimte op de SD-kaart.

### Stap 3: SD-Kaart Voorbereiden

1. Format SD-kaart als **FAT32**
2. Kopie bestanden naar **root** van kaart (geen submappen)
3. Zorg dat bestandsnamen exact `1.mp3`...`9.mp3` zijn

## 📤 Naar ESP32 Zetten

### Via mpremote (makkelijk)

```bash
cd path/to/AlarmKlok/music

# Kopie alle MP3's naar ESP32 root
python -m mpremote connect COM7 cp 1.mp3 :1.mp3 + cp 2.mp3 :2.mp3 + cp 3.mp3 :3.mp3 + \
  cp 4.mp3 :4.mp3 + cp 5.mp3 :5.mp3 + cp 6.mp3 :6.mp3 + \
  cp 7.mp3 :7.mp3 + cp 8.mp3 :8.mp3 + cp 9.mp3 :9.mp3 + reset
```

### Via SD-Kaart (als je DFPlayer met SD-kaart gebruikt)

1. Zet SD-kaart in je computer
2. Kopie `1.mp3`...`9.mp3` naar root
3. Zet terug in DFPlayer

## 🔧 Hulpscript

Een Python-script om bestanden automatisch hernoemd:

```bash
python prepare_music.py --input-dir ./downloads --output-dir ./music
```

(Script staat in dit project: zie `tools/prepare_music.py`)

## ✅ Testen

1. Ga naar web UI (http://alarmklok)
2. Kies "Alarm testen" → selecteer tone (1-9)
3. Audio moet ~15 sec afspelen
4. Controleer animatie synchroon loopt

## 🎚️ Volume Aanpassen

In web UI → **Alarm Settings** → **Volume Slider**

Op ESP32 code:
```python
DFPLAYER_VOLUME = 20  # 0-30, default 15
```

## 🐛 Troubleshooting

| Probleem | Oplossing |
|----------|-----------|
| Geen geluid | SD-kaart niet herkend; check DFPlayer verkabelingen |
| Verkeerde track | Bestand hernoemd; zorg `1.mp3`...`9.mp3` |
| Gekraak/vertragingen | Bitrate te hoog; converteer naar 128kbps |
| Zeer zacht | Volume te laag; verhoog in web UI |

---

**Next:** Zie `tools/prepare_music.py` voor geautomatiseerde voorbereiding!
