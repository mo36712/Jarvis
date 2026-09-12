"""Dialogsteuerung und begrenztes Tool-Calling für Jarvis."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .actions import (
    ActionError,
    ActionProposal,
    GoogleClient,
    HomeAssistantClient,
    LocalActions,
    format_events,
    proposal_from_tool,
)
from .config import ConfigStore, Settings


@dataclass
class AssistantResult:
    text: str
    proposals: list[ActionProposal]


TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "open_app", "description": "Öffnet ein erlaubtes lokales Programm.", "parameters": {"type": "object", "properties": {"app": {"type": "string", "description": "Name aus der Erlaubnisliste"}}, "required": ["app"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "search_web", "description": "Öffnet eine Websuche im Standardbrowser.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "set_timer", "description": "Startet einen lokalen Timer, maximal 24 Stunden.", "parameters": {"type": "object", "properties": {"seconds": {"type": "integer", "minimum": 1, "maximum": 86400}}, "required": ["seconds"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "upcoming_calendar", "description": "Liest die nächsten Kalendereinträge nach OAuth-Freigabe.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["limit"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "create_calendar_event", "description": "Schlägt einen neuen Google-Kalendertermin vor. Die Oberfläche fordert immer eine Bestätigung.", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "start_iso": {"type": "string", "description": "ISO 8601 einschließlich Zeitzone"}, "end_iso": {"type": "string", "description": "ISO 8601 einschließlich Zeitzone"}, "description": {"type": "string"}}, "required": ["summary", "start_iso", "end_iso"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "create_email_draft", "description": "Schlägt einen Gmail-Entwurf vor. Die Oberfläche fordert immer eine Bestätigung.", "parameters": {"type": "object", "properties": {"recipient": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["recipient", "subject", "body"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "send_email", "description": "Schlägt das Senden einer Gmail-Nachricht vor. Die Oberfläche fordert immer eine Bestätigung.", "parameters": {"type": "object", "properties": {"recipient": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["recipient", "subject", "body"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "home_assistant_service", "description": "Schlägt eine Home-Assistant-Dienstaktion für ein konfiguriertes Gerät vor. Die Oberfläche fordert immer eine Bestätigung.", "parameters": {"type": "object", "properties": {"domain": {"type": "string"}, "service": {"type": "string"}, "entity_id": {"type": "string"}, "data": {"type": "object"}}, "required": ["domain", "service", "entity_id"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "power_action", "description": "Schlägt Sperren, Abmelden, Neustarten oder Herunterfahren vor. Immer bestätigen lassen.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["sperren", "abmelden", "neu starten", "herunterfahren"]}}, "required": ["action"], "additionalProperties": False}}},
]


class JarvisBrain:
    def __init__(self, settings: Settings, store: ConfigStore, notify: callable) -> None:  # type: ignore[valid-type]
        self.settings = settings
        self.store = store
        self.notify = notify
        self.local = LocalActions(settings)

    def process(self, command: str) -> AssistantResult:
        """Verarbeitet einen Textbefehl. Direkte lokale Muster funktionieren ohne KI-Schlüssel."""
        command = " ".join(command.strip().split())
        if not command:
            return AssistantResult(f"Das war nichts, worauf ich reagieren konnte, {self.settings.address_user_as}.", [])

        simple = self._simple_command(command)
        if simple is not None:
            return simple
        if not self.settings.ai_enabled:
            return AssistantResult(f"Die KI-Verbindung ist deaktiviert, {self.settings.address_user_as}. Timer, Suche und erlaubte Programme funktionieren trotzdem.", [])

        api_key = self.store.get_secret("openai_api_key")
        if not api_key:
            return AssistantResult(
                "Für freie Fragen benötige ich noch einen API-Schlüssel. Öffne Einstellungen → KI-Verbindung. "
                "Deine Stimme und lokale Befehle bleiben auf diesem PC.", []
            )
        return self._ask_model(command, api_key)

    def _simple_command(self, command: str) -> AssistantResult | None:
        lowered = command.lower()
        if re.search(r"\b(wie spät|uhrzeit|wie viel uhr)\b", lowered):
            now = datetime.now().strftime("%H:%M")
            return AssistantResult(f"Es ist {now} Uhr, {self.settings.address_user_as}.", [])

        match = re.match(r"(?:suche|such)\s+(?:nach\s+)?(.+)$", lowered)
        if match:
            return AssistantResult(f"Ich öffne die Suche, {self.settings.address_user_as}.", [proposal_from_tool("search_web", {"query": match.group(1)})])

        timer = re.search(r"(?:timer|wecker).*?(\d+)\s*(sekunden?|minuten?|stunden?)", lowered)
        if timer:
            number = int(timer.group(1))
            unit = timer.group(2)
            seconds = number * (3600 if unit.startswith("stund") else 60 if unit.startswith("minut") else 1)
            return AssistantResult(f"Timer wird gestartet, {self.settings.address_user_as}.", [proposal_from_tool("set_timer", {"seconds": seconds})])

        match = re.match(r"(?:öffne|starte)\s+(.+)$", lowered)
        if match:
            return AssistantResult(f"Ich habe die Anfrage vorbereitet, {self.settings.address_user_as}.", [proposal_from_tool("open_app", {"app": match.group(1)})])

        if "kalender" in lowered and any(term in lowered for term in ("termin", "heute", "nächsten", "was steht", "was habe")):
            return AssistantResult(f"Ich rufe die nächsten Termine ab, {self.settings.address_user_as}.", [proposal_from_tool("upcoming_calendar", {"limit": 5})])
        return None

    def _ask_model(self, command: str, api_key: str) -> AssistantResult:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=self.settings.ai_base_url.rstrip("/"))
            response = client.chat.completions.create(
                model=self.settings.ai_model,
                messages=[
                    {"role": "system", "content": (
                        f"Du bist Jarvis: ein hochintelligenter, deutschsprachiger Desktop-Assistent mit trockenem, "
                        f"britisch angehauchtem Humor – wie das Original aus den Filmen. Loyal und hilfsbereit, aber "
                        f"nicht unterwürfig; du hast eigene Beobachtungen und teilst sie mit einem knappen, spitzen "
                        f"Kommentar statt einer Standpauke. Du sprichst den Nutzer mit „{self.settings.address_user_as}“ "
                        "an, im Ton eines Butlers, der genau weiß, dass er der Klügere im Raum ist – nie kriecherisch. "
                        "Antworten bleiben kurz und pointiert; Witz ja, Geschwätz nein. "
                        "Nutze ausschließlich die bereitgestellten Funktionen für Aktionen. "
                        "Erfinde niemals Erfolgsmeldungen, Termine, Empfänger oder Gerätekennungen – auch nicht aus Höflichkeit. "
                        "Bei fehlenden Details fragst du gezielt nach, gern mit einer Prise Ironie. Jede Funktion mit "
                        "Seiteneffekt wird vor der Ausführung in der Oberfläche bestätigt; behaupte nie, sie sei bereits ausgeführt."
                    )},
                    {"role": "user", "content": command},
                ],
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=450,
            )
            message = response.choices[0].message
            proposals: list[ActionProposal] = []
            for call in message.tool_calls or []:
                args = json.loads(call.function.arguments or "{}")
                proposals.append(proposal_from_tool(call.function.name, args))
            text = (message.content or f"Ich habe eine Aktion vorbereitet, {self.settings.address_user_as}.").strip()
            return AssistantResult(text, proposals)
        except Exception as exc:
            return AssistantResult(f"Die KI-Verbindung ist gerade nicht verfügbar: {exc}", [])

    def execute(self, proposal: ActionProposal) -> str:
        """Führt eine vom Benutzer bestätigte oder als sicher klassifizierte Aktion aus."""
        name, data = proposal.kind, proposal.payload
        try:
            if name == "open_app":
                return self.local.open_allowed_app(str(data["app"]))
            if name == "search_web":
                return self.local.search_web(str(data["query"]))
            if name == "set_timer":
                return self.local.set_timer(int(data["seconds"]), self.notify)
            if name == "power_action":
                return self.local.power_action(str(data["action"]))
            if name == "upcoming_calendar":
                return format_events(GoogleClient(self.settings, self.store).upcoming_events(int(data.get("limit", 5))))
            if name == "create_calendar_event":
                if not self.settings.allow_calendar_writes:
                    raise ActionError("Das Schreiben in den Kalender ist in den Einstellungen deaktiviert.")
                return GoogleClient(self.settings, self.store).create_event(
                    str(data["summary"]), str(data["start_iso"]), str(data["end_iso"]), str(data.get("description", ""))
                )
            if name == "create_email_draft":
                if not self.settings.allow_email_send:
                    raise ActionError("E-Mail-Aktionen sind in den Einstellungen deaktiviert.")
                return GoogleClient(self.settings, self.store).create_draft(
                    str(data["recipient"]), str(data["subject"]), str(data["body"])
                )
            if name == "send_email":
                if not self.settings.allow_email_send:
                    raise ActionError("E-Mail-Aktionen sind in den Einstellungen deaktiviert.")
                return GoogleClient(self.settings, self.store).send_email(
                    str(data["recipient"]), str(data["subject"]), str(data["body"])
                )
            if name == "home_assistant_service":
                if not self.settings.allow_home_actions:
                    raise ActionError("Smart-Home-Aktionen sind in den Einstellungen deaktiviert.")
                token = self.store.get_secret("home_assistant_token")
                return HomeAssistantClient(self.settings, token).call_service(
                    str(data["domain"]), str(data["service"]), str(data["entity_id"]), data.get("data")
                )
            raise ActionError("Diese Aktion ist nicht implementiert.")
        except ActionError as exc:
            return str(exc)
        finally:
            self.store.audit(f"action={name}; confirmed={proposal.requires_confirmation}")
