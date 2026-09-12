"""Lokale Audioein- und -ausgabe für Jarvis.

Die Anwendung speichert keine Roh-Audioaufnahmen. Vosk verarbeitet die Frames im
Arbeitsspeicher und übergibt nur den erkannten Befehl an die Befehlslogik.
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .config import Settings


class AudioUnavailableError(RuntimeError):
    """Wird bei fehlendem Mikrofon oder Sprachmodell ausgelöst."""


class SpeechOutput:
    """Serielle Textausgabe – wahlweise über die Windows-Stimme (pyttsx3) oder über
    eine lokal geklonte eigene Stimme (XTTS-v2, komplett offline nach dem ersten
    Modell-Download). Schlägt die geklonte Stimme fehl oder ist nicht eingerichtet,
    übernimmt für die gesamte Sitzung automatisch die Windows-Stimme.
    """

    def __init__(self, settings: Settings) -> None:
        self.language = (settings.language or "de")[:2].lower()
        self.engine_kind = settings.voice_engine if settings.voice_engine in ("pyttsx3", "xtts") else "pyttsx3"
        self.voice_sample_path = (settings.xtts_voice_sample_path or "").strip()
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-tts")
        self._thread.start()

    def say(self, text: str) -> None:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if cleaned:
            self._queue.put(cleaned)

    def stop(self) -> None:
        self._queue.put(None)

    def _run(self) -> None:
        if self.engine_kind == "xtts" and self.voice_sample_path:
            # Gibt False zurück, wenn die geklonte Stimme nicht geladen werden konnte
            # (z. B. Pakete fehlen, keine GPU/zu wenig RAM, Datei nicht gefunden) –
            # dann läuft die Sitzung nahtlos mit der Windows-Stimme weiter.
            if self._run_xtts():
                return
        self._run_pyttsx3()

    def _run_pyttsx3(self) -> None:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            for voice in engine.getProperty("voices"):
                voice_id = (getattr(voice, "id", "") + " " + getattr(voice, "name", "")).lower()
                if self.language in voice_id or "german" in voice_id or "deutsch" in voice_id:
                    engine.setProperty("voice", voice.id)
                    break
            while True:
                text = self._queue.get()
                if text is None:
                    engine.stop()
                    return
                engine.say(text)
                engine.runAndWait()
        except Exception:
            # Die Oberfläche bleibt auch ohne verfügbare Systemstimme benutzbar –
            # Text weiterhin in der Warteschlange leeren, statt den Thread sterben zu lassen.
            while True:
                if self._queue.get() is None:
                    return

    def _run_xtts(self) -> bool:
        """Lädt XTTS-v2 einmalig und spricht danach jeden Text mit der geklonten Stimme.

        Läuft komplett lokal: kein API-Key, kein Kreditlimit. Auf einer aktuellen
        Nvidia-GPU antwortet das in ein bis zwei Sekunden pro Satz; ohne GPU (reine
        CPU) kann eine Antwort mehrere Sekunden dauern – Jarvis bleibt dabei aber
        nutzbar, nur nicht ganz so spontan wie mit ElevenLabs.
        """
        try:
            os.environ.setdefault("COQUI_TOS_AGREED", "1")  # akzeptiert die nicht-kommerzielle Coqui-Lizenz automatisch

            if not Path(self.voice_sample_path).is_file():
                return False

            import sounddevice as sd
            import torch
            from TTS.api import TTS

            device = "cuda" if torch.cuda.is_available() else "cpu"
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
            supported_languages = set(getattr(tts, "languages", None) or [])
            language = self.language if self.language in supported_languages else "de"
        except Exception:
            return False

        while True:
            text = self._queue.get()
            if text is None:
                return True
            try:
                wav = tts.tts(text=text, speaker_wav=self.voice_sample_path, language=language)
                sd.play(wav, samplerate=24_000)
                sd.wait()
            except Exception:
                # Nur dieser eine Satz ist fehlgeschlagen; die Sitzung läuft weiter.
                continue


class LocalVoiceLoop:
    """Vosk-basierter, lokaler Wake-Word- und Befehlsschleife.

    Im Ruhezustand wird auf das einzelne Wort „Jarvis“ eingeschränkt. Nach dem
    Wake-Word erfasst das Modell einen Befehl bis zu einer Sprechpause. Ein
    optionales Picovoice-Modell kann zukünftig ergänzend eingebunden werden,
    benötigt aber einen separaten Nutzerzugang.
    """

    SAMPLE_RATE = 16_000

    def __init__(
        self,
        model_path: str,
        wake_word: str,
        listen_timeout_seconds: int,
        microphone_device: int | None,
        on_status: Callable[[str], None],
        on_wake: Callable[[], None],
        on_command: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        self.model_path = Path(model_path).expanduser()
        self.wake_word = wake_word.lower().strip()
        self.listen_timeout_seconds = max(3, listen_timeout_seconds)
        self.microphone_device = microphone_device
        self.on_status = on_status
        self.on_wake = on_wake
        self.on_command = on_command
        self.on_error = on_error
        self._audio: queue.Queue[bytes] = queue.Queue(maxsize=48)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream = None
        self._awake = False
        self._awake_at = 0.0
        self._lock = threading.Lock()

    @staticmethod
    def available_microphones() -> list[tuple[int, str]]:
        try:
            import sounddevice as sd
        except ImportError:
            return []
        result: list[tuple[int, str]] = []
        for index, device in enumerate(sd.query_devices()):
            if int(device.get("max_input_channels", 0)) > 0:
                result.append((index, str(device.get("name", f"Mikrofon {index}"))))
        return result

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        if not self.model_path.is_dir():
            raise AudioUnavailableError(
                "Das deutsche Sprachmodell fehlt. Öffne Einstellungen und wähle den entpackten Vosk-Modellordner aus."
            )
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-voice")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._stream is not None:
            try:
                self._stream.abort()
                self._stream.close()
            except Exception:
                pass
        self._stream = None
        self._thread = None
        with self._lock:
            self._awake = False
        self.on_status("Sprachsteuerung aus")

    def _callback(self, indata, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
        if status:
            # Kurzzeitige Überläufe dürfen die Dauerschleife nicht beenden.
            pass
        try:
            self._audio.put_nowait(bytes(indata))
        except queue.Full:
            try:
                self._audio.get_nowait()
            except queue.Empty:
                pass

    def _new_recognizer(self, model, grammar: list[str] | None = None):  # type: ignore[no-untyped-def]
        from vosk import KaldiRecognizer

        if grammar:
            return KaldiRecognizer(model, self.SAMPLE_RATE, json.dumps(grammar, ensure_ascii=False))
        return KaldiRecognizer(model, self.SAMPLE_RATE)

    def _go_to_sleep(self, reason: str = "Bereit – sage Jarvis") -> None:
        with self._lock:
            self._awake = False
        self.on_status(reason)

    def _wake(self) -> None:
        with self._lock:
            self._awake = True
            self._awake_at = time.monotonic()
        self.on_status("Ich höre zu …")
        self.on_wake()

    def _run(self) -> None:
        try:
            import sounddevice as sd
            from vosk import Model, SetLogLevel

            SetLogLevel(-1)
            model = Model(str(self.model_path))
            wake_recognizer = self._new_recognizer(model, [self.wake_word, "[unk]"])
            command_recognizer = self._new_recognizer(model)
            self.on_status("Bereit – sage Jarvis")
            self._stream = sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=8_000,
                device=self.microphone_device,
                dtype="int16",
                channels=1,
                callback=self._callback,
            )
            self._stream.start()

            while not self._stop_event.is_set():
                try:
                    frame = self._audio.get(timeout=0.25)
                except queue.Empty:
                    with self._lock:
                        timed_out = self._awake and (time.monotonic() - self._awake_at > self.listen_timeout_seconds)
                    if timed_out:
                        self._go_to_sleep("Zeit abgelaufen – sage Jarvis")
                        wake_recognizer = self._new_recognizer(model, [self.wake_word, "[unk]"])
                    continue

                with self._lock:
                    awake = self._awake
                if not awake:
                    final = wake_recognizer.AcceptWaveform(frame)
                    payload = wake_recognizer.Result() if final else wake_recognizer.PartialResult()
                    text = json.loads(payload).get("text") or json.loads(payload).get("partial", "")
                    if self.wake_word in text.lower().split():
                        self._wake()
                        command_recognizer = self._new_recognizer(model)
                    continue

                if command_recognizer.AcceptWaveform(frame):
                    text = json.loads(command_recognizer.Result()).get("text", "").strip()
                    if text:
                        self._go_to_sleep("Verarbeite Befehl …")
                        self.on_command(text)
                        wake_recognizer = self._new_recognizer(model, [self.wake_word, "[unk]"])
                    else:
                        self._go_to_sleep()
                        wake_recognizer = self._new_recognizer(model, [self.wake_word, "[unk]"])
        except Exception as exc:
            self.on_error(f"Mikrofon/Spracherkennung nicht gestartet: {exc}")
            self._go_to_sleep("Sprachsteuerung nicht verfügbar")
        finally:
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
