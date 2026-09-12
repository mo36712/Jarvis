"""PySide6-Oberfläche für Jarvis."""
from __future__ import annotations

import concurrent.futures
import html
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .actions import ActionProposal
from .audio import AudioUnavailableError, LocalVoiceLoop, SpeechOutput
from .brain import AssistantResult, JarvisBrain
from .config import ConfigStore, Settings


class Bridge(QtCore.QObject):
    status = QtCore.Signal(str)
    command = QtCore.Signal(str)
    error = QtCore.Signal(str)
    result = QtCore.Signal(object)
    action_done = QtCore.Signal(str)


class SettingsDialog(QtWidgets.QDialog):
    """Konfiguriert lokale Pfade und Geheimnisse; zeigt geheime Werte nie im Klartext wieder an."""

    def __init__(self, settings: Settings, store: ConfigStore, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.settings = settings
        self.store = store
        self.setWindowTitle("Jarvis – Einstellungen")
        self.setMinimumWidth(640)
        layout = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)

        # KI-Verbindung
        ai = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(ai)
        self.ai_enabled = QtWidgets.QCheckBox("KI-Verbindung aktivieren")
        self.ai_enabled.setChecked(settings.ai_enabled)
        self.ai_url = QtWidgets.QLineEdit(settings.ai_base_url)
        self.ai_model = QtWidgets.QLineEdit(settings.ai_model)
        self.api_key = QtWidgets.QLineEdit()
        self.api_key.setPlaceholderText("Nur ändern, wenn ein neuer Schlüssel gespeichert werden soll")
        self.api_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        form.addRow(self.ai_enabled)
        form.addRow("API-Basisadresse", self.ai_url)
        form.addRow("Modell", self.ai_model)
        form.addRow("API-Schlüssel", self.api_key)
        hint = QtWidgets.QLabel("Der Schlüssel wird im Windows-Anmeldeinformationsspeicher abgelegt, nicht in der Projektdatei.")
        hint.setWordWrap(True)
        form.addRow(hint)
        tabs.addTab(ai, "KI")

        # Stimme
        voice = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(voice)
        self.voice_engine_combo = QtWidgets.QComboBox()
        self.voice_engine_combo.addItem("Windows-Stimme (sofort startklar, robotischer Klang)", "pyttsx3")
        self.voice_engine_combo.addItem("Eigene geklonte Stimme – lokal, unbegrenzt (XTTS)", "xtts")
        engine_index = self.voice_engine_combo.findData(settings.voice_engine)
        self.voice_engine_combo.setCurrentIndex(max(0, engine_index))
        self.xtts_sample_path = QtWidgets.QLineEdit(settings.xtts_voice_sample_path)
        self.xtts_sample_path.setPlaceholderText("WAV-Datei mit 6–30 Sekunden sauberer Sprachaufnahme")
        browse_sample = QtWidgets.QPushButton("Datei auswählen …")
        browse_sample.clicked.connect(self._choose_voice_sample)
        sample_row = QtWidgets.QHBoxLayout()
        sample_row.addWidget(self.xtts_sample_path)
        sample_row.addWidget(browse_sample)
        form.addRow("Sprachausgabe", self.voice_engine_combo)
        form.addRow("Stimmprobe (nur für geklonte Stimme)", self._row_widget(sample_row))
        xtts_note = QtWidgets.QLabel(
            "Die geklonte Stimme läuft komplett auf diesem PC, ohne Kreditlimit. Beim ersten Einsatz lädt sie "
            "einmalig ein ca. 2 GB großes Modell herunter (Internet nötig, danach nicht mehr). Mit Nvidia-GPU "
            "antwortet sie flott, rein auf der CPU kann eine Antwort mehrere Sekunden dauern. Nur für den "
            "persönlichen Gebrauch gedacht (nicht-kommerzielle Lizenz)."
        )
        xtts_note.setWordWrap(True)
        form.addRow(xtts_note)
        self.vosk_path = QtWidgets.QLineEdit(settings.vosk_model_path)
        browse_vosk = QtWidgets.QPushButton("Ordner auswählen …")
        browse_vosk.clicked.connect(self._choose_vosk)
        vosk_row = QtWidgets.QHBoxLayout()
        vosk_row.addWidget(self.vosk_path)
        vosk_row.addWidget(browse_vosk)
        self.wake_word = QtWidgets.QLineEdit(settings.wake_word)
        self.address = QtWidgets.QLineEdit(settings.address_user_as)
        self.timeout = QtWidgets.QSpinBox()
        self.timeout.setRange(3, 60)
        self.timeout.setValue(settings.listen_timeout_seconds)
        self.mic_combo = QtWidgets.QComboBox()
        self.mic_combo.addItem("Windows-Standardmikrofon", None)
        for index, name in LocalVoiceLoop.available_microphones():
            self.mic_combo.addItem(f"{index}: {name}", index)
        selected = self.mic_combo.findData(settings.microphone_device)
        self.mic_combo.setCurrentIndex(max(0, selected))
        form.addRow("Vosk-Modellordner", self._row_widget(vosk_row))
        form.addRow("Wake-Word", self.wake_word)
        form.addRow("Anrede", self.address)
        form.addRow("Zuhörzeit nach Wake-Word", self.timeout)
        form.addRow("Mikrofon", self.mic_combo)
        note = QtWidgets.QLabel("Im Ruhezustand wertet Jarvis lokal nur das Wake-Word aus. Gesprochene Befehle werden nicht als Audiodatei gespeichert.")
        note.setWordWrap(True)
        form.addRow(note)
        tabs.addTab(voice, "Stimme")

        # Integrationen
        integrations = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(integrations)
        self.google_creds = QtWidgets.QLineEdit(settings.google_client_secrets_path)
        choose_google = QtWidgets.QPushButton("Datei auswählen …")
        choose_google.clicked.connect(self._choose_google)
        google_row = QtWidgets.QHBoxLayout()
        google_row.addWidget(self.google_creds)
        google_row.addWidget(choose_google)
        self.home_url = QtWidgets.QLineEdit(settings.home_assistant_url)
        self.home_token = QtWidgets.QLineEdit()
        self.home_token.setPlaceholderText("Nur ändern, wenn ein neuer Token gespeichert werden soll")
        self.home_token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.allow_calendar = QtWidgets.QCheckBox("Kalendertermine anlegen erlauben")
        self.allow_calendar.setChecked(settings.allow_calendar_writes)
        self.allow_email = QtWidgets.QCheckBox("E-Mail-Entwürfe und Versand erlauben")
        self.allow_email.setChecked(settings.allow_email_send)
        self.allow_home = QtWidgets.QCheckBox("Smart-Home-Aktionen erlauben")
        self.allow_home.setChecked(settings.allow_home_actions)
        form.addRow("Google OAuth credentials.json", self._row_widget(google_row))
        form.addRow("Home-Assistant-Adresse", self.home_url)
        form.addRow("Home-Assistant-Token", self.home_token)
        form.addRow(self.allow_calendar)
        form.addRow(self.allow_email)
        form.addRow(self.allow_home)
        integration_note = QtWidgets.QLabel("Jarvis öffnet die jeweilige OAuth-Freigabe erst bei der ersten Aktion. E-Mails, Termine und Smart-Home-Änderungen werden immer einzeln bestätigt.")
        integration_note.setWordWrap(True)
        form.addRow(integration_note)
        tabs.addTab(integrations, "Integrationen")

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _row_widget(layout: QtWidgets.QLayout) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget

    def _choose_vosk(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Vosk-Modellordner auswählen", self.vosk_path.text())
        if path:
            self.vosk_path.setText(path)

    def _choose_voice_sample(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Stimmprobe auswählen", self.xtts_sample_path.text(), "WAV-Datei (*.wav)"
        )
        if path:
            self.xtts_sample_path.setText(path)

    def _choose_google(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "credentials.json auswählen", self.google_creds.text(), "JSON-Datei (*.json)")
        if path:
            self.google_creds.setText(path)

    def collect(self) -> Settings:
        new = Settings.from_dict(self.settings.__dict__)
        new.ai_enabled = self.ai_enabled.isChecked()
        new.ai_base_url = self.ai_url.text().strip() or "https://api.openai.com/v1"
        new.ai_model = self.ai_model.text().strip()
        new.voice_engine = self.voice_engine_combo.currentData() or "pyttsx3"
        new.xtts_voice_sample_path = self.xtts_sample_path.text().strip()
        new.vosk_model_path = self.vosk_path.text().strip()
        new.wake_word = self.wake_word.text().strip().lower() or "jarvis"
        new.address_user_as = self.address.text().strip() or "Sir"
        new.listen_timeout_seconds = self.timeout.value()
        new.microphone_device = self.mic_combo.currentData()
        new.google_client_secrets_path = self.google_creds.text().strip()
        new.home_assistant_url = self.home_url.text().strip()
        new.allow_calendar_writes = self.allow_calendar.isChecked()
        new.allow_email_send = self.allow_email.isChecked()
        new.allow_home_actions = self.allow_home.isChecked()
        return new

    def save_secrets(self) -> None:
        if self.api_key.text().strip():
            self.store.set_secret("openai_api_key", self.api_key.text().strip())
        if self.home_token.text().strip():
            self.store.set_secret("home_assistant_token", self.home_token.text().strip())


class JarvisWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.store = ConfigStore()
        self.settings = self.store.load()
        self.bridge = Bridge()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="jarvis-work")
        self.speech = SpeechOutput(self.settings)
        self.voice: LocalVoiceLoop | None = None
        self.brain = JarvisBrain(self.settings, self.store, self._notification)
        self._build_ui()
        self._connect_signals()
        self._create_voice_loop()
        self._append("system", "System bereit. Gib einen Befehl ein oder starte die Sprachsteuerung, Sir.")

    def _build_ui(self) -> None:
        self.setWindowTitle("JARVIS // DESKTOP ASSISTANT")
        self.setMinimumSize(920, 680)
        self.resize(1080, 760)
        self.setWindowIcon(QtGui.QIcon())
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        header = QtWidgets.QHBoxLayout()
        title_box = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("JARVIS")
        title.setObjectName("title")
        subtitle = QtWidgets.QLabel("PERSÖNLICHER DESKTOP-ASSISTENT // LOKALER SCHUTZMODUS")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.status_badge = QtWidgets.QLabel("●  BEREIT")
        self.status_badge.setObjectName("status")
        header.addWidget(self.status_badge)
        settings_button = QtWidgets.QPushButton("Einstellungen")
        settings_button.clicked.connect(self.open_settings)
        header.addWidget(settings_button)
        root.addLayout(header)

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setObjectName("accentLine")
        root.addWidget(line)

        self.history = QtWidgets.QTextBrowser()
        self.history.setOpenExternalLinks(False)
        self.history.setReadOnly(True)
        self.history.setObjectName("history")
        root.addWidget(self.history, 1)

        voice_card = QtWidgets.QFrame()
        voice_card.setObjectName("voiceCard")
        row = QtWidgets.QHBoxLayout(voice_card)
        self.voice_indicator = QtWidgets.QLabel("◉")
        self.voice_indicator.setObjectName("voiceIndicator")
        row.addWidget(self.voice_indicator)
        self.voice_label = QtWidgets.QLabel("Sprachsteuerung ist ausgeschaltet")
        row.addWidget(self.voice_label, 1)
        self.voice_button = QtWidgets.QPushButton("Sprachsteuerung starten")
        self.voice_button.setObjectName("primaryButton")
        self.voice_button.clicked.connect(self.toggle_voice)
        row.addWidget(self.voice_button)
        test_voice = QtWidgets.QPushButton("Stimme testen")
        test_voice.clicked.connect(self.test_voice)
        row.addWidget(test_voice)
        root.addWidget(voice_card)

        input_row = QtWidgets.QHBoxLayout()
        self.command_input = QtWidgets.QLineEdit()
        self.command_input.setPlaceholderText("Befehl eingeben …  z. B. „Öffne Rechner“ oder „Wie spät ist es?“")
        self.command_input.returnPressed.connect(self.submit_text)
        input_row.addWidget(self.command_input, 1)
        send = QtWidgets.QPushButton("Senden")
        send.setObjectName("primaryButton")
        send.clicked.connect(self.submit_text)
        input_row.addWidget(send)
        root.addLayout(input_row)

        self.setStyleSheet("""
            QMainWindow, QWidget { background: #071116; color: #dceff3; font-family: 'Segoe UI'; font-size: 14px; }
            #title { color: #58e5ff; font-size: 34px; font-weight: 700; letter-spacing: 5px; }
            #subtitle { color: #6d9098; font-size: 10px; letter-spacing: 2px; }
            #status { color: #8af6c9; border: 1px solid #1f725c; background: #0b2928; border-radius: 12px; padding: 6px 12px; font-weight: 700; }
            #accentLine { color: #1a8291; background: #1a8291; max-height: 1px; }
            #history { background: #091b21; border: 1px solid #17414a; border-radius: 12px; padding: 12px; selection-background-color: #145563; }
            #voiceCard { background: #0a2027; border: 1px solid #19505c; border-radius: 12px; padding: 4px; }
            #voiceIndicator { color: #57e1ff; font-size: 28px; padding: 0 8px; }
            QLineEdit { background: #0b1d23; border: 1px solid #275660; border-radius: 8px; padding: 12px; color: #effcff; }
            QLineEdit:focus { border: 1px solid #58e5ff; }
            QPushButton { background: #12313a; border: 1px solid #285f6b; border-radius: 8px; padding: 9px 14px; color: #dceff3; }
            QPushButton:hover { background: #184653; border-color: #58e5ff; }
            #primaryButton { background: #0d6d82; border-color: #55e1ff; color: white; font-weight: 700; }
            #primaryButton:hover { background: #1290a9; }
            QTabWidget::pane { border: 1px solid #275660; } QTabBar::tab { padding: 8px 14px; background: #0b1d23; } QTabBar::tab:selected { background: #0d6d82; }
            QCheckBox { padding: 4px; } QSpinBox, QComboBox { background: #0b1d23; border: 1px solid #275660; border-radius: 6px; padding: 6px; }
        """)

    def _connect_signals(self) -> None:
        self.bridge.status.connect(self._set_status)
        self.bridge.command.connect(self._process_command)
        self.bridge.error.connect(lambda message: self._append("error", message))
        self.bridge.result.connect(self._handle_result)
        self.bridge.action_done.connect(self._handle_action_done)

    def _create_voice_loop(self) -> None:
        if self.voice and self.voice.running:
            self.voice.stop()
        self.voice = LocalVoiceLoop(
            self.settings.vosk_model_path, self.settings.wake_word, self.settings.listen_timeout_seconds,
            self.settings.microphone_device, self.bridge.status.emit,
            lambda: self.speech.say(f"Ja, {self.settings.address_user_as}?"),
            self.bridge.command.emit, self.bridge.error.emit,
        )

    def _append(self, role: str, message: str) -> None:
        colors = {"user": "#c8f4ff", "jarvis": "#58e5ff", "system": "#9ab8bf", "error": "#ff9d86", "action": "#8af6c9"}
        names = {"user": "SIR", "jarvis": "JARVIS", "system": "SYSTEM", "error": "HINWEIS", "action": "AKTION"}
        safe = html.escape(message).replace("\n", "<br>")
        self.history.append(f'<p style="margin: 9px 0;"><span style="color:{colors[role]}; font-weight:700; letter-spacing:1px;">{names[role]}</span><br>{safe}</p>')
        bar = self.history.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set_status(self, text: str) -> None:
        self.voice_label.setText(text)
        active = "höre" in text.lower() or "bereit" in text.lower()
        self.status_badge.setText("●  AKTIV" if active else "●  BEREIT")

    def _notification(self, text: str) -> None:
        self.bridge.action_done.emit(text)

    def toggle_voice(self) -> None:
        if self.voice and self.voice.running:
            self.voice.stop()
            self.voice_button.setText("Sprachsteuerung starten")
            return
        try:
            assert self.voice is not None
            self.voice.start()
            self.voice_button.setText("Sprachsteuerung stoppen")
        except AudioUnavailableError as exc:
            self._append("error", str(exc))
            self.open_settings()

    def test_voice(self) -> None:
        self.speech.say(
            f"Test, Test. Ich bin online und höre, {self.settings.address_user_as}. "
            "Falls das gerade nach der Windows-Stimme klingt statt nach meiner geklonten Stimme, "
            "lohnt ein Blick in die Einstellungen."
        )

    def submit_text(self) -> None:
        command = self.command_input.text().strip()
        if not command:
            return
        self.command_input.clear()
        self._process_command(command)

    def _process_command(self, command: str) -> None:
        self._append("user", command)
        future = self.executor.submit(self.brain.process, command)
        future.add_done_callback(lambda task: self.bridge.result.emit(task.result()) if not task.exception() else self.bridge.error.emit(str(task.exception())))

    def _handle_result(self, result: AssistantResult) -> None:
        self._append("jarvis", result.text)
        self.speech.say(result.text)
        for proposal in result.proposals:
            if proposal.requires_confirmation:
                self._confirm_and_execute(proposal)
            else:
                self._execute(proposal)

    def _confirm_and_execute(self, proposal: ActionProposal) -> None:
        answer = QtWidgets.QMessageBox.question(
            self, f"Bestätigung: {proposal.title}",
            f"<b>{html.escape(proposal.description)}</b><br><br>Diese Aktion kann etwas außerhalb von Jarvis verändern. Soll sie ausgeführt werden?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self._execute(proposal)
        else:
            self._append("system", f"Aktion abgebrochen: {proposal.title}.")
            self.store.audit(f"action={proposal.kind}; confirmed=False")

    def _execute(self, proposal: ActionProposal) -> None:
        self._append("system", f"Ausführung: {proposal.description}")
        future = self.executor.submit(self.brain.execute, proposal)
        future.add_done_callback(lambda task: self.bridge.action_done.emit(task.result()) if not task.exception() else self.bridge.error.emit(str(task.exception())))

    def _handle_action_done(self, text: str) -> None:
        self._append("action", text)
        self.speech.say(text)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.store, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            was_running = bool(self.voice and self.voice.running)
            if was_running and self.voice:
                self.voice.stop()
            self.settings = dialog.collect()
            try:
                dialog.save_secrets()
                self.store.save(self.settings)
                self.brain = JarvisBrain(self.settings, self.store, self._notification)
                self.speech.stop()
                self.speech = SpeechOutput(self.settings)
                self._create_voice_loop()
                self._append("system", "Einstellungen gespeichert.")
                if was_running and self.voice:
                    self.voice.start()
                    self.voice_button.setText("Sprachsteuerung stoppen")
            except Exception as exc:
                self._append("error", f"Einstellungen konnten nicht vollständig gespeichert werden: {exc}")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.voice:
            self.voice.stop()
        self.speech.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        event.accept()


def run() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("JarvisAI")
    app.setOrganizationName("JarvisAI")
    window = JarvisWindow()
    window.show()
    return app.exec()
