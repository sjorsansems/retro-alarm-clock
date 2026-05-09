#!/usr/bin/env python3
import re

with open('retro_georgy_alarm_klok_v6.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: Muziek herhaal logica
old_section = '''        # --- DFPlayer: herhaal het geselecteerde lied totdat alarm eindigt ---
        if self.dfplayer is not None:
            try:
                track = int(self.active_tone)
                dfvol = max(0, min(30, int(self.volume * 30 // 100) + self._alarm_boss_level() * 3))
                self.dfplayer.set_volume(dfvol)
                
                # Speel altijd: dit zorgt ervoor dat als het nummer is afgelopen, het opnieuw start
                if not self._dfplayer_playing:
                    self.dfplayer.play_mp3(track)
                    print("DFPlayer: speel track {} op volume {}".format(track, dfvol))
                    self._dfplayer_playing = True
                else:
                    # Muziek loopt. Check elke seconde of we opnieuw moeten starten
                    # (DFPlayer geeft geen status terug, dus we spelen gewoon opnieuw)
                    pass
            except Exception as e:
                print("! DFPlayer play fout:", e)
            return'''

new_section = '''        # --- DFPlayer: herhaal het geselecteerde lied totdat alarm eindigt ---
        if self.dfplayer is not None:
            try:
                track = int(self.active_tone)
                dfvol = max(0, min(30, int(self.volume * 30 // 100) + self._alarm_boss_level() * 3))
                self.dfplayer.set_volume(dfvol)
                
                # Herhaal muziek elke ~20 sec (MP3's zijn meestal 10-20s)
                elapsed_ms = max(0, time.ticks_diff(now_ms, self.alarm_started_ms))
                elapsed_sec = elapsed_ms // 1000
                
                if not self._dfplayer_playing or (elapsed_sec > 0 and elapsed_sec % 20 == 0):
                    self.dfplayer.play_mp3(track)
                    print("DFPlayer: speel track {}, volume {}, alarm_sec: {}".format(track, dfvol, elapsed_sec))
                    self._dfplayer_playing = True
            except Exception as e:
                print("! DFPlayer play fout:", e)
            return'''

content = content.replace(old_section, new_section)

with open('retro_georgy_alarm_klok_v6.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ Muziek herhaal fix toegepast")
