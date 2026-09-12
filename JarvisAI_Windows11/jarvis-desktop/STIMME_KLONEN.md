# Eigene Stimme & neue Persönlichkeit – was sich geändert hat

## 1. Was neu ist

- **Neue Sprachausgabe-Option:** Jarvis kann jetzt entweder wie bisher die
  Windows-Stimme (`pyttsx3`) nutzen, oder eine **eigene geklonte Stimme**
  (XTTS-v2, Open Source). Die geklonte Stimme läuft komplett auf deinem PC –
  kein API-Key, kein Kreditlimit, kein "Sprachkontingent ausgeschöpft" mehr.
- **Neue Persönlichkeit:** Jarvis antwortet jetzt trocken-witzig statt steif
  förmlich – angelehnt an den Film-Jarvis. Die Anrede bleibt frei einstellbar
  (Einstellungen → Stimme → "Anrede", Standard: "Sir").
- Schlägt die geklonte Stimme mal fehl (z. B. weil ein Paket fehlt), springt
  Jarvis automatisch und ohne Absturz auf die Windows-Stimme zurück.

## 2. Ehrliche Einordnung, bevor du loslegst

- **Lizenz:** XTTS-v2 steht unter der Coqui Public Model License – **kostenlos,
  aber nur für den persönlichen/nicht-kommerziellen Gebrauch.** Für dich als
  privaten Jarvis genau richtig; nicht weiterverkaufen oder in ein bezahltes
  Produkt einbauen.
- **Geschwindigkeit:** Mit einer Nvidia-Grafikkarte (ab ca. 4 GB VRAM)
  antwortet die geklonte Stimme in ein bis zwei Sekunden – spürbar, aber
  flüssig. **Ohne GPU, nur auf der CPU**, kann eine Antwort mehrere Sekunden
  dauern. Für ein schnelles "Ja?" beim Aufwachen bleibt die Windows-Stimme
  daher oft die bessere Wahl; für längere, "echte" Antworten lohnt sich die
  geklonte Stimme trotzdem.
- **Erster Start:** Beim allerersten Einsatz lädt XTTS einmalig ein rund 2 GB
  großes Modell herunter (Internet nötig). Danach läuft alles offline.

## 3. Einrichtung, Schritt für Schritt

### Schritt 1 – Pakete installieren

`coqui-tts` steht bereits in `requirements.txt`. **PyTorch installierst du
separat**, weil sich der richtige Befehl je nach Hardware unterscheidet:

- **Mit Nvidia-GPU:** Schau auf https://pytorch.org/get-started/locally/ nach
  dem passenden Befehl für deine CUDA-Version, z. B.:
  ```
  pip install torch --index-url https://download.pytorch.org/whl/cu124
  ```
- **Ohne GPU (nur CPU):**
  ```
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  ```

Danach wie gewohnt:
```
pip install -r requirements.txt
```

### Schritt 2 – Eigene Stimme aufnehmen

Im Projektordner:
```
python record_voice_sample.py 20
```
Das nimmt 20 Sekunden auf und speichert sie z. B. unter
`C:\Users\DeinName\jarvis_voice_sample.wav`. Sprich dabei normal und
zusammenhängend (siehe Tipps im Skript-Kopf).

### Schritt 3 – In Jarvis eintragen

1. Jarvis öffnen → **Einstellungen** → Tab **Stimme**.
2. Bei "Sprachausgabe" **"Eigene geklonte Stimme – lokal, unbegrenzt (XTTS)"**
   auswählen.
3. Bei "Stimmprobe" die eben aufgenommene WAV-Datei auswählen.
4. Speichern.
5. Auf **"Stimme testen"** klicken. Der erste Test lädt das Modell (dauert je
   nach Internet und Hardware etwas), danach ist er schnell.

### Schritt 4 (optional) – Verpackung als .exe

Für den laufenden Betrieb per `python main.py` funktioniert das sofort. Willst
du die geklonte Stimme auch in die per PyInstaller gebaute `.exe` packen,
wird das Paket wegen PyTorch/XTTS deutlich größer (mehrere GB) und die
PyInstaller-Konfiguration muss die Modelldateien mit einschließen. Für den
Anfang empfehlen wir: im Entwicklungsbetrieb (`python main.py`) mit der
geklonten Stimme arbeiten, für die verteilte `.exe` vorerst bei der
Windows-Stimme bleiben.

## 4. Die Persönlichkeit weiter anpassen

Der Charakter steckt im System-Prompt in `jarvis/brain.py`, in der Methode
`_ask_model`. Dort kannst du den Ton weiter feinjustieren – z. B. weniger
Sarkasmus, mehr Wärme, oder eine ganz andere Anrede über das Feld "Anrede" in
den Einstellungen (z. B. "Chef", "Boss" oder dein Name statt "Sir").
