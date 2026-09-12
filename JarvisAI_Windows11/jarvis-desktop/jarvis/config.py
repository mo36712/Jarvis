"""Lokale Konfiguration für Jarvis.

Nicht geheime Einstellungen liegen im Benutzerprofil. API-Schlüssel und Tokens werden
über das Betriebssystem-Schlüsselbund abgelegt; sie gehören nie in die config.json.
"""
from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import keyring

APP_NAME = "JarvisAI"
SERVICE_NAME = "JarvisAI.Desktop"


def app_data_dir() -> Path:
    """Gibt einen beschreibbaren Ordner ohne Administratorrechte zurück."""
    if os.getenv("JARVIS_PORTABLE") == "1":
        return Path.cwd() / "jarvis_data"
    if platform.system() == "Windows":
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


@dataclass
class Settings:
    # KI (OpenAI-kompatible Schnittstelle; Schlüssel separat im Schlüsselbund)
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4.1-mini"
    ai_enabled: bool = True

    # Stimme und Sprache
    language: str = "de-DE"
    wake_word: str = "jarvis"
    vosk_model_path: str = ""
    microphone_device: int | None = None
    listen_timeout_seconds: int = 10
    autostart_listening: bool = False
    address_user_as: str = "Sir"

    # Sprachausgabe-Engine: "pyttsx3" (Windows-Stimme, sofort einsatzbereit) oder
    # "xtts" (eigene geklonte Stimme, läuft komplett lokal, unbegrenzt nutzbar).
    voice_engine: str = "pyttsx3"
    # Pfad zu einer WAV-Datei mit einer sauberen Aufnahme der zu klonenden Stimme
    # (6–30 Sekunden reichen). Nur relevant, wenn voice_engine == "xtts".
    xtts_voice_sample_path: str = ""

    # Sicherheitsverhalten: Standardmäßig ist jede schreibende Aktion bestätigt.
    confirm_external_actions: bool = True
    allow_calendar_writes: bool = True
    allow_email_send: bool = True
    allow_home_actions: bool = True

    # Integrationen (Token separat im Schlüsselbund)
    home_assistant_url: str = ""
    google_client_secrets_path: str = ""
    google_token_path: str = ""

    # Lokale Steuerung: Nur erlaubte Kurzbefehle; keine freie Shell-Ausführung.
    allowed_apps: dict[str, str] = field(default_factory=lambda: {
        "editor": "notepad.exe",
        "notepad": "notepad.exe",
        "rechner": "calc.exe",
        "taschenrechner": "calc.exe",
        "dateien": "explorer.exe",
        "explorer": "explorer.exe",
        "einstellungen": "ms-settings:",
    })

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Settings":
        known = {name for name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in raw.items() if key in known})


class ConfigStore:
    """Persistiert Einstellungen und Geheimnisse im Benutzerkontext."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or app_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "config.json"
        self.audit_path = self.data_dir / "audit.log"

    def load(self) -> Settings:
        if not self.path.exists():
            settings = Settings()
            self.save(settings)
            return settings
        try:
            return Settings.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError(f"Konfiguration kann nicht gelesen werden: {exc}") from exc

    def save(self, settings: Settings) -> None:
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp_path.replace(self.path)

    def get_secret(self, name: str) -> str:
        try:
            return keyring.get_password(SERVICE_NAME, name) or ""
        except keyring.errors.KeyringError:
            return ""

    def set_secret(self, name: str, value: str) -> None:
        try:
            if value:
                keyring.set_password(SERVICE_NAME, name, value)
            else:
                try:
                    keyring.delete_password(SERVICE_NAME, name)
                except keyring.errors.PasswordDeleteError:
                    pass
        except keyring.errors.KeyringError as exc:
            raise RuntimeError(
                "Der Windows-Anmeldeinformationsspeicher ist nicht verfügbar. "
                "Bitte starte die App im angemeldeten Benutzerkonto erneut."
            ) from exc

    def audit(self, event: str) -> None:
        """Schreibt absichtlich keine Spracheingaben, Inhalte oder Schlüssel ins Protokoll."""
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp}\t{event}\n")

    @property
    def google_token_file(self) -> Path:
        return self.data_dir / "google_token.json"

    @property
    def integration_dir(self) -> Path:
        path = self.data_dir / "integrations"
        path.mkdir(exist_ok=True)
        return path
