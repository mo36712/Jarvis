"""Rauchtest ohne Mikrofon, Netzwerk oder persönliche Zugangsdaten."""
from __future__ import annotations

import tempfile
from pathlib import Path

from jarvis.actions import proposal_from_tool
from jarvis.brain import JarvisBrain
from jarvis.config import ConfigStore, Settings


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = ConfigStore(Path(tmp))
        settings = Settings(ai_enabled=False)
        brain = JarvisBrain(settings, store, lambda _: None)

        result = brain.process("Wie spät ist es?")
        assert "Es ist" in result.text and not result.proposals

        result = brain.process("Öffne Rechner")
        assert len(result.proposals) == 1
        assert result.proposals[0].kind == "open_app"
        assert not result.proposals[0].requires_confirmation

        result = brain.process("Starte einen Timer für 2 Minuten")
        assert result.proposals[0].payload["seconds"] == 120

        email = proposal_from_tool("send_email", {
            "recipient": "max@example.com", "subject": "Test", "body": "Hallo"
        })
        assert email.requires_confirmation

        power = proposal_from_tool("power_action", {"action": "herunterfahren"})
        assert power.requires_confirmation

    print("Rauchtest erfolgreich")


if __name__ == "__main__":
    main()
