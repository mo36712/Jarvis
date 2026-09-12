"""Ausführbare Aktionen mit enger, expliziter Erlaubnisliste.

Dieses Modul nimmt keine Shell-Befehle aus Sprache oder KI-Modell entgegen. Für
externe Änderungen wird zuerst ein ``ActionProposal`` an die Oberfläche gegeben.
"""
from __future__ import annotations

import base64
import os
import subprocess
import threading
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus, urlparse

import requests

from .config import ConfigStore, Settings


@dataclass(frozen=True)
class ActionProposal:
    """Eine von Jarvis beschriebene, aber noch nicht ausgeführte Aktion."""

    kind: str
    title: str
    description: str
    payload: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = True


class ActionError(RuntimeError):
    pass


class LocalActions:
    """Lokale Aktionen ohne freie Befehlsausführung."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def open_allowed_app(self, app_name: str) -> str:
        requested = app_name.lower().strip()
        executable = self.settings.allowed_apps.get(requested)
        if not executable:
            allowed = ", ".join(sorted(self.settings.allowed_apps))
            raise ActionError(f"„{app_name}“ ist nicht freigegeben. Erlaubt sind: {allowed}.")
        if executable.startswith("ms-settings:"):
            os.startfile(executable)  # type: ignore[attr-defined]  # Windows Shell URI
        else:
            subprocess.Popen([executable], shell=False)  # nosec B603: fixed allow-list value
        return f"Ich öffne {app_name}, Sir."

    @staticmethod
    def search_web(query: str) -> str:
        cleaned = " ".join(query.split())
        if not cleaned:
            raise ActionError("Die Suchanfrage ist leer.")
        webbrowser.open_new_tab(f"https://www.google.com/search?q={quote_plus(cleaned)}")
        return f"Ich öffne die Suche nach „{cleaned}“, Sir."

    @staticmethod
    def open_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ActionError("Es sind nur vollständige http- oder https-Adressen erlaubt.")
        webbrowser.open_new_tab(url)
        return "Ich habe die Webseite geöffnet, Sir."

    @staticmethod
    def set_timer(seconds: int, on_done: Callable[[str], None]) -> str:
        seconds = max(1, min(int(seconds), 86_400))
        threading.Timer(seconds, lambda: on_done("Der Timer ist abgelaufen, Sir.")).start()
        minutes, remainder = divmod(seconds, 60)
        spoken = f"{minutes} Minuten" if minutes and not remainder else f"{seconds} Sekunden"
        return f"Timer für {spoken} gestartet, Sir."

    @staticmethod
    def power_action(action: str) -> str:
        # Windows akzeptiert diese Aufrufe ohne Administratorrechte; sie werden
        # jedoch ausnahmslos durch die zentrale Bestätigung geschützt.
        commands = {
            "sperren": ["rundll32.exe", "user32.dll,LockWorkStation"],
            "abmelden": ["shutdown.exe", "/l"],
            "neu starten": ["shutdown.exe", "/r", "/t", "10"],
            "herunterfahren": ["shutdown.exe", "/s", "/t", "10"],
        }
        command = commands.get(action)
        if not command:
            raise ActionError("Unbekannte Energieaktion.")
        subprocess.Popen(command, shell=False)  # nosec B603: fixed mapping
        return f"{action.capitalize()} wurde angefordert, Sir."


class HomeAssistantClient:
    """Kleiner Client für eine bewusst konfigurierte Home-Assistant-Instanz."""

    def __init__(self, settings: Settings, token: str) -> None:
        base = settings.home_assistant_url.rstrip("/")
        if not base or not token:
            raise ActionError("Home Assistant ist noch nicht verbunden.")
        parsed = urlparse(base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ActionError("Die Home-Assistant-Adresse ist ungültig.")
        self.base = base
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def states(self) -> list[dict[str, Any]]:
        try:
            response = requests.get(f"{self.base}/api/states", headers=self.headers, timeout=8)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise ActionError(f"Home Assistant ist nicht erreichbar: {exc}") from exc

    def call_service(self, domain: str, service: str, entity_id: str, data: dict[str, Any] | None = None) -> str:
        if not domain.replace("_", "").isalnum() or not service.replace("_", "").isalnum():
            raise ActionError("Ungültiger Home-Assistant-Dienst.")
        if not entity_id or "." not in entity_id or not all(c.isalnum() or c in "_." for c in entity_id):
            raise ActionError("Ungültige Gerätekennung.")
        body = dict(data or {})
        body["entity_id"] = entity_id
        try:
            response = requests.post(
                f"{self.base}/api/services/{domain}/{service}", headers=self.headers, json=body, timeout=10
            )
            response.raise_for_status()
            return "Die Smart-Home-Aktion wurde ausgeführt, Sir."
        except requests.RequestException as exc:
            raise ActionError(f"Home-Assistant-Aktion fehlgeschlagen: {exc}") from exc


class GoogleClient:
    """Google OAuth für Kalender und Gmail im lokalen Benutzerprofil."""

    SCOPES = [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.send",
    ]

    def __init__(self, settings: Settings, store: ConfigStore) -> None:
        self.settings = settings
        self.store = store

    def _credentials(self):  # type: ignore[no-untyped-def]
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise ActionError("Google-Bibliotheken fehlen. Bitte führe setup_windows.ps1 aus.") from exc

        token_path = Path(self.settings.google_token_path) if self.settings.google_token_path else self.store.google_token_file
        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), self.SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                secrets_path = Path(self.settings.google_client_secrets_path).expanduser()
                if not secrets_path.is_file():
                    raise ActionError("Die Google-OAuth-Datei credentials.json wurde noch nicht ausgewählt.")
                flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), self.SCOPES)
                creds = flow.run_local_server(port=0)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def upcoming_events(self, limit: int = 5) -> list[dict[str, Any]]:
        try:
            from googleapiclient.discovery import build
            service = build("calendar", "v3", credentials=self._credentials())
            now = datetime.now(timezone.utc).isoformat()
            return service.events().list(
                calendarId="primary", timeMin=now, maxResults=max(1, min(limit, 10)),
                singleEvents=True, orderBy="startTime"
            ).execute().get("items", [])
        except Exception as exc:
            raise ActionError(f"Kalender konnte nicht gelesen werden: {exc}") from exc

    def create_event(self, summary: str, start_iso: str, end_iso: str, description: str = "") -> str:
        try:
            from googleapiclient.discovery import build
            event = {
                "summary": summary,
                "description": description,
                "start": {"dateTime": start_iso},
                "end": {"dateTime": end_iso},
            }
            service = build("calendar", "v3", credentials=self._credentials())
            created = service.events().insert(calendarId="primary", body=event).execute()
            return f"Termin „{summary}“ wurde angelegt: {created.get('htmlLink', '')}"
        except Exception as exc:
            raise ActionError(f"Termin konnte nicht angelegt werden: {exc}") from exc

    def create_draft(self, recipient: str, subject: str, body: str) -> str:
        try:
            from googleapiclient.discovery import build
            message = EmailMessage()
            message["To"] = recipient
            message["Subject"] = subject
            message.set_content(body)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            service = build("gmail", "v1", credentials=self._credentials())
            draft = service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
            return f"Entwurf erstellt (ID: {draft.get('id', 'unbekannt')})."
        except Exception as exc:
            raise ActionError(f"E-Mail-Entwurf konnte nicht erstellt werden: {exc}") from exc

    def send_email(self, recipient: str, subject: str, body: str) -> str:
        try:
            from googleapiclient.discovery import build
            message = EmailMessage()
            message["To"] = recipient
            message["Subject"] = subject
            message.set_content(body)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            service = build("gmail", "v1", credentials=self._credentials())
            sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            return f"E-Mail wurde gesendet (ID: {sent.get('id', 'unbekannt')})."
        except Exception as exc:
            raise ActionError(f"E-Mail konnte nicht gesendet werden: {exc}") from exc


def format_events(events: list[dict[str, Any]]) -> str:
    if not events:
        return "Für die nächsten Termine ist nichts eingetragen, Sir."
    entries = []
    for event in events:
        when = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "")
        entries.append(f"{when}: {event.get('summary', 'Ohne Titel')}")
    return "Ihre nächsten Termine sind: " + "; ".join(entries) + "."


def proposal_from_tool(name: str, args: dict[str, Any]) -> ActionProposal:
    """Übersetzt KI-Tool-Aufrufe in prüfbare Anzeigen für die Oberfläche."""
    if name == "open_app":
        app = str(args.get("app", ""))
        return ActionProposal(name, "Programm öffnen", f"Programm „{app}“ öffnen", {"app": app}, False)
    if name == "search_web":
        query = str(args.get("query", ""))
        return ActionProposal(name, "Websuche öffnen", f"Suche nach „{query}“ in deinem Browser öffnen", {"query": query}, False)
    if name == "set_timer":
        seconds = int(args.get("seconds", 0))
        return ActionProposal(name, "Timer starten", f"Timer für {seconds} Sekunden starten", {"seconds": seconds}, False)
    if name == "upcoming_calendar":
        return ActionProposal(name, "Kalender lesen", "Die nächsten Kalendereinträge abrufen", {"limit": int(args.get("limit", 5))}, False)
    if name == "create_calendar_event":
        title = str(args.get("summary", ""))
        return ActionProposal(name, "Termin anlegen", f"Neuen Termin „{title}“ im Kalender anlegen", args, True)
    if name == "create_email_draft":
        return ActionProposal(name, "E-Mail-Entwurf erstellen", f"Entwurf an {args.get('recipient', '')} erstellen", args, True)
    if name == "send_email":
        return ActionProposal(name, "E-Mail senden", f"E-Mail an {args.get('recipient', '')} senden", args, True)
    if name == "home_assistant_service":
        return ActionProposal(name, "Smart Home steuern", f"{args.get('domain', '')}.{args.get('service', '')} für {args.get('entity_id', '')}", args, True)
    if name == "power_action":
        action = str(args.get("action", ""))
        return ActionProposal(name, "Windows-Aktion", f"Windows {action}", {"action": action}, True)
    raise ActionError(f"Nicht erlaubte Aktion: {name}")
