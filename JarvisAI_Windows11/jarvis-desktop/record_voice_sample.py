"""Nimmt eine kurze, saubere Sprachprobe für die eigene geklonte Stimme auf.

Nutzung:
    python record_voice_sample.py [Sekunden] [Ausgabedatei]

Ohne Angaben werden 20 Sekunden aufgenommen und als "jarvis_voice_sample.wav"
im Benutzer-Home-Verzeichnis gespeichert.

Tipps für eine gute Stimmprobe:
  - Ruhiger Raum, möglichst ohne Hintergrundgeräusche (kein Radio/TV/Lüfter).
  - Normal und zusammenhängend sprechen – kein Flüstern, kein Schreien.
  - Am besten einen kurzen Text vorlesen (z. B. einen Absatz aus einem Buch
    oder einer Nachrichtenseite), keine abgehackten Einzelwörter.
  - 10–30 Sekunden reichen für XTTS-v2 völlig aus; mehr bringt kaum noch etwas.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

SAMPLE_RATE = 24_000  # passt gut zur Ausgabe-Samplerate von XTTS


def record(seconds: int, output_path: Path) -> None:
    import sounddevice as sd

    print(f"Aufnahme startet in 3 Sekunden – dann {seconds} Sekunden am Stück sprechen.")
    sd.sleep(3000)
    print("... Aufnahme läuft ...")

    frames: list[bytes] = []

    def callback(indata, frame_count, time_info, status) -> None:  # type: ignore[no-untyped-def]
        frames.append(bytes(indata))

    with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback):
        sd.sleep(seconds * 1000)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # int16 = 2 Byte pro Sample
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(b"".join(frames))

    print(f"\nFertig. Gespeichert unter: {output_path}")
    print("Trag diesen Pfad jetzt in Jarvis ein unter: Einstellungen → Stimme → Stimmprobe.")


def main() -> None:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.home() / "jarvis_voice_sample.wav"
    record(seconds, output)


if __name__ == "__main__":
    main()
