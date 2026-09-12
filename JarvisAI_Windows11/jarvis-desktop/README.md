# JARVIS // Desktop Assistant für Windows 11

**JarvisAI** ist eine deutschsprachige Desktop-Anwendung für Windows 11. Sie hört lokal auf das Wake-Word **„Jarvis“**, spricht dich standardmäßig mit **„Sir“** an, beantwortet Texteingaben und kann nach konfigurierter Freigabe Programme öffnen, suchen, Timer setzen, Kalender lesen bzw. Termine anlegen, Gmail-Entwürfe erstellen oder senden sowie Home Assistant steuern.

> **Datenschutzprinzip:** Die fortlaufende Wake-Word-Erkennung und die Spracherkennung laufen mit Vosk auf deinem PC. Es werden keine Audiodateien gespeichert. Nur freie KI-Fragen werden an den von dir in den Einstellungen gewählten OpenAI-kompatiblen KI-Anbieter gesendet.

## Funktionsumfang

| Bereich | Enthaltene Funktion | Sicherheitsverhalten |
|---|---|---|
| **Sprache** | Lokales Wake-Word „Jarvis“, deutsche Offline-Spracherkennung, Windows-Sprachausgabe | Sprachaufnahmen werden nicht gespeichert. |
| **KI-Dialog** | Textdialog und freie Fragen über einen konfigurierbaren OpenAI-kompatiblen Anbieter | Der API-Schlüssel liegt im Windows-Anmeldeinformationsspeicher, nicht im Quellcode. |
| **PC-Steuerung** | Notepad, Rechner, Explorer und Einstellungen öffnen; Websuche; lokale Timer | Keine freie Terminal- oder Shell-Ausführung. Die Programmliste ist fest begrenzt. |
| **Kalender** | Anstehende Google-Kalendertermine lesen und Termine anlegen | Google OAuth-Freigabe; das Anlegen wird immer bestätigt. |
| **E-Mail** | Gmail-Entwurf erstellen oder E-Mail senden | Google OAuth-Freigabe; Entwurf und Versand werden immer bestätigt. |
| **Smart Home** | Home-Assistant-Geräte über einen Dienstaufruf steuern | Jede Geräteänderung wird einzeln bestätigt. |
| **Windows-Aktionen** | Sperren, Abmelden, Neustart und Herunterfahren | Jede Aktion wird einzeln bestätigt; keine Umgehung von UAC oder Administratorrechten. |

## Voraussetzungen

Du brauchst **Windows 11**, ein funktionsfähiges Mikrofon und **Python 3.10 oder neuer**. Python kann für das eigene Benutzerkonto installiert werden; Administratorrechte sind hierfür nicht Teil dieser Anwendung. Für die Offline-Spracherkennung lädt das Setup optional das kompakte deutsche Vosk-Modell (`vosk-model-small-de-0.15`, etwa 45 MB). Vosk unterstützt Deutsch sowie lokale Verarbeitung; die Vosk-Modellübersicht empfiehlt die kleineren Modelle ausdrücklich für Desktop-Anwendungen.[1] [2]

Für freie KI-Antworten benötigst du einen eigenen API-Schlüssel bei einem OpenAI-kompatiblen Anbieter. **Sende diesen Schlüssel nicht im Chat und trage ihn nicht in eine Datei ein.** Nach der Einrichtung wird er in der App unter `Einstellungen → KI` eingegeben und über den Windows-Anmeldeinformationsspeicher abgelegt.

## Installation ohne Administratorrechte

Entpacke das ZIP in einen eigenen Ordner, zum Beispiel `Dokumente\JarvisAI`. Öffne dort PowerShell und führe folgenden Befehl aus:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -DownloadVoskModel
```

Das Skript erstellt eine isolierte virtuelle Python-Umgebung **innerhalb des Projektordners**, installiert alle Abhängigkeiten nur dort und lädt das deutsche Sprachmodell in den Unterordner `models`. Danach startest du die App durch Doppelklick auf `start_jarvis.cmd`.

Für eine lokale EXE-Version führst du statt dessen einmalig aus:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -DownloadVoskModel -BuildExe
```

Danach liegt die ausführbare Datei unter `dist\JarvisAI\JarvisAI.exe`. PyInstaller paketiert Python-Anwendungen als Anwendung; eine projektlokale Installation ist von einer systemweiten Installation zu unterscheiden, für die andernfalls Administratorrechte erforderlich sein können.[3]

## Erste Einrichtung

Starte Jarvis und öffne **Einstellungen**. Im Tab **Stimme** wählst du den entpackten Vosk-Modellordner aus, normalerweise:

```text
<dein Jarvis-Ordner>\models\vosk-model-small-de-0.15
```

Aktiviere danach die Sprachsteuerung. Der Status wechselt zu **„Bereit – sage Jarvis“**. Sage zunächst deutlich „Jarvis“, warte auf „Ja, Sir?“ und sprich dann deinen Befehl. Diese Zweischritt-Variante reduziert Fehlaktivierungen und vermeidet, dass nach dem Wake-Word noch Teile eines langen Satzes verloren gehen.

| Beispiel | Wirkung |
|---|---|
| „Jarvis“ → „Öffne Rechner“ | Öffnet den Windows-Rechner aus der Erlaubnisliste. |
| „Jarvis“ → „Suche nach Wetter in Berlin“ | Öffnet eine Google-Suche im Standardbrowser. |
| „Jarvis“ → „Stelle einen Timer für 10 Minuten“ | Startet einen lokalen Timer. |
| „Wie spät ist es?“ | Antwortet vollständig lokal ohne KI-API. |
| „Was habe ich in meinem Kalender?“ | Liest nach Google-Freigabe die nächsten Kalendereinträge. |

## KI-Verbindung konfigurieren

Unter **Einstellungen → KI** gibst du die Basisadresse und das Modell deines Anbieters ein. Bei der originalen OpenAI-API ist die Basisadresse `https://api.openai.com/v1`. Die Anwendung ruft das standardisierte Chat-Completions-Format mit eng begrenzten Werkzeugen auf. Das Modell kann **keinen** freien Shell-Befehl ausführen und erhält keine gespeicherten Zugangsschlüssel.

Für einen lokalen Betrieb ohne externe KI kannst du die Option **„KI-Verbindung aktivieren“** ausschalten. Wake-Word, einfache Zeitabfragen, Timer, Suche und die Erlaubnisliste für Programme funktionieren trotzdem. Freie Fragen und das Verstehen komplexer Integrationsbefehle benötigen dann naturgemäß keine externe KI, stehen aber nicht zur Verfügung.

## Google Kalender und Gmail verbinden

Jarvis verwendet die offizielle Google-OAuth-Freigabe für Desktop-Apps. In deiner Google Cloud Console legst du ein Projekt an, aktivierst **Google Calendar API** und **Gmail API**, erstellst einen OAuth-Client vom Typ **Desktop-App** und lädst die Datei `credentials.json` herunter. Die offizielle Google-Anleitung beschreibt diesen Desktop-OAuth-Ablauf und die lokale Token-Ablage.[4]

Wähle diese `credentials.json` anschließend unter `Einstellungen → Integrationen` aus. Bei der ersten Kalender- oder Gmail-Aktion öffnet Jarvis die Google-Freigabe im Browser. Der Aktualisierungstoken wird lokal im Jarvis-Benutzerordner abgelegt. Für Gmail erzeugt die App MIME-konforme, base64url-kodierte Nachrichten und nutzt die vorgesehenen Gmail-Endpunkte für Entwürfe bzw. Versand.[5]

> **Wichtig:** Kalendertermine, E-Mail-Entwürfe und E-Mails werden nicht automatisch ausgeführt. Vor jeder externen Änderung zeigt Jarvis einen Bestätigungsdialog mit der konkreten Aktion.

## Home Assistant verbinden

Trage unter `Einstellungen → Integrationen` die lokale URL deiner Home-Assistant-Instanz ein, beispielsweise `http://homeassistant.local:8123`, und speichere einen Long-Lived Access Token im vorgesehenen Passwortfeld. Ein solcher Token wird laut Home-Assistant-Dokumentation im Profil der Instanz erzeugt und bei REST-Aufrufen als `Authorization: Bearer …` übertragen.[6]

Jarvis ruft ausschließlich den konfigurierten Host auf. Bei einer Aktion wie „Schalte das Licht im Arbeitszimmer an“ kann die KI einen vorgeschlagenen Dienstaufruf erzeugen, aber die Oberfläche zeigt zunächst den Dienst und die Gerätekennung und fordert deine Bestätigung. Home Assistant führt tatsächliche Geräteaktionen über `POST /api/services/<domain>/<service>` aus; ein bloßes Ändern eines Zustands würde ein Gerät nicht steuern.[6]

## Sicherheitsmodell und Grenzen

Die App fordert keine Administratorrechte an und versucht nicht, Schutzmechanismen zu umgehen. Deshalb sind Systemänderungen, die Windows selbst erhöhte Rechte verlangen, nicht verfügbar. Die folgenden Schutzmaßnahmen sind fest in die Anwendung eingebaut:

| Schutzmaßnahme | Umsetzung |
|---|---|
| **Keine freie Codeausführung** | Ein KI-Modell kann ausschließlich feste, schema-validierte Funktionen vorschlagen. Es kann keine PowerShell-, CMD- oder Python-Befehle ausführen. |
| **Bestätigung vor Folgen** | Smart-Home-Aktionen, Gmail-Entwürfe, E-Mail-Versand, Kalendereinträge sowie Abmelden, Neustart und Herunterfahren benötigen immer einen sichtbaren Klick. |
| **Lokale Schlüsselablage** | API-Schlüssel und Home-Assistant-Token werden über `keyring` im Windows-Anmeldeinformationsspeicher abgelegt, nicht in `config.json`. |
| **Datenminimierung** | Das Protokoll notiert nur Art und Zeitpunkt von Aktionsentscheidungen, keine Sprachaufnahme, E-Mail-Inhalte, Kalenderdaten oder Tokens. |
| **Begrenzte Programmstarts** | Standardmäßig sind nur `notepad.exe`, `calc.exe`, `explorer.exe` und Windows-Einstellungen verfügbar. |

## Projektstruktur

```text
JarvisAI/
├── main.py                    # Startpunkt
├── jarvis/
│   ├── audio.py               # lokales Wake-Word, Vosk und Sprachausgabe
│   ├── brain.py               # Dialoglogik und streng begrenzte Tool-Aufrufe
│   ├── actions.py             # lokale, Google- und Home-Assistant-Aktionen
│   ├── config.py              # Konfiguration, Schlüsselbund und Audit-Protokoll
│   └── ui.py                  # Desktop-Oberfläche
├── setup_windows.ps1          # Benutzerinstallation und optionales EXE-Build
├── start_jarvis.cmd           # App starten
├── requirements.txt
└── tests/smoke_test.py        # Test ohne Mikrofon, Netzwerk oder persönliche Daten
```

## Prüfung und Fehlerbehebung

Der enthaltene Rauchtest prüft Befehlsklassifikation und Bestätigungsregeln, ohne ein Mikrofon, ein Onlinekonto oder einen Schlüssel zu benutzen:

```powershell
.\.venv\Scripts\python.exe tests\smoke_test.py
```

Wenn die Sprachsteuerung nicht startet, überprüfe zuerst den Modellpfad und das in Windows ausgewählte Standardmikrofon. Wenn Jarvis das Wake-Word zu selten erkennt, spreche „Jarvis“ mit kurzer Pause vor dem Befehl. Das deutsche Vosk-Kleinmodell ist leichtgewichtig; für besonders anspruchsvolle Diktate stellt Vosk auch deutlich größere, speicherintensivere deutsche Modelle bereit.[1]

## Referenzen

[1] [Vosk – verfügbare Sprachmodelle](https://alphacephei.com/vosk/models)  
[2] [Vosk – Offline-Spracherkennung und unterstützte Sprachen](https://alphacephei.com/vosk/)  
[3] [PyInstaller – Installation und benutzerlokale Pfade](https://pyinstaller.org/en/stable/installation.html)  
[4] [Google Calendar API – Python-Quickstart und Desktop OAuth](https://developers.google.com/workspace/calendar/api/quickstart/python)  
[5] [Gmail API – E-Mails erstellen und senden](https://developers.google.com/workspace/gmail/api/guides/sending)  
[6] [Home Assistant – REST API](https://developers.home-assistant.io/docs/api/rest/)
