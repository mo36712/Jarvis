<#
JarvisAI – Einrichtung für Windows 11 ohne Administratorrechte.

Ausführung im entpackten Projektordner:
  powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -DownloadVoskModel
#>
[CmdletBinding()]
param(
    [switch]$DownloadVoskModel,
    [switch]$BuildExe
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{ Command = "py"; Arguments = @("-3") }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{ Command = "python"; Arguments = @() }
    }
    throw "Python 3.10 oder neuer fehlt. Installiere Python für dein Benutzerkonto von python.org oder dem Microsoft Store und starte dieses Skript erneut."
}

$Python = Get-PythonCommand
Write-Host "[1/4] Erzeuge lokale Python-Umgebung …" -ForegroundColor Cyan
& $Python.Command @($Python.Arguments) -m venv .venv
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host "[2/4] Installiere Abhängigkeiten nur in diesem Projektordner …" -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

if ($DownloadVoskModel) {
    $ModelsDir = Join-Path $ProjectRoot "models"
    $ModelDir = Join-Path $ModelsDir "vosk-model-small-de-0.15"
    $Archive = Join-Path $ModelsDir "vosk-model-small-de-0.15.zip"
    if (-not (Test-Path $ModelDir)) {
        New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
        Write-Host "[3/4] Lade das deutsche Offline-Sprachmodell (ca. 45 MB) …" -ForegroundColor Cyan
        Invoke-WebRequest -Uri "https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip" -OutFile $Archive
        Expand-Archive -Path $Archive -DestinationPath $ModelsDir -Force
        Remove-Item $Archive -Force
    } else {
        Write-Host "[3/4] Sprachmodell bereits vorhanden." -ForegroundColor DarkCyan
    }
} else {
    Write-Host "[3/4] Sprachmodell wird übersprungen. Du kannst es später mit -DownloadVoskModel nachladen." -ForegroundColor DarkCyan
}

if ($BuildExe) {
    Write-Host "[4/4] Erzeuge JarvisAI.exe …" -ForegroundColor Cyan
    & $VenvPython -m PyInstaller --noconfirm --clean --windowed --name JarvisAI --add-data "jarvis;jarvis" main.py
    Write-Host "Fertig: dist\JarvisAI\JarvisAI.exe" -ForegroundColor Green
} else {
    Write-Host "[4/4] Überspringe EXE-Paketierung. Starte die App mit start_jarvis.cmd." -ForegroundColor DarkCyan
}

Write-Host "Einrichtung abgeschlossen. Es wurden keine Administratorrechte benötigt." -ForegroundColor Green
