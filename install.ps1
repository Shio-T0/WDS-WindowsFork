# WDS - Wallpaper Display for Spotify (Windows)
# Installation script

$ErrorActionPreference = "Stop"

function Info($msg)  { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Err($msg)   { Write-Host "[ERROR] $msg" -ForegroundColor Red }

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigDir = Join-Path $env:APPDATA "spotify-wallpaper"
$ConfigFile = Join-Path $ConfigDir "config.toml"
$VideoDir = Join-Path $env:USERPROFILE "Videos\spotify-wallpapers"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  WDS - Wallpaper Display for Spotify" -ForegroundColor Cyan
Write-Host "  Windows Installation Script" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Check winget ─────────────────────────────────────────────────────────────

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Err "winget is not installed. It comes with Windows 10 1809+ and Windows 11."
    Err "Install it from the Microsoft Store ('App Installer'), then re-run this script."
    exit 1
}
Ok "winget is available"

# ── Install system dependencies ──────────────────────────────────────────────

$deps = @(
    @{ Id = "Python.Python.3.11";            Name = "Python 3.11" },
    @{ Id = "astral-sh.uv";                  Name = "uv (Python package manager)" },
    @{ Id = "rocksdanister.LivelyWallpaper"; Name = "Lively Wallpaper" },
    @{ Id = "Gyan.FFmpeg";                   Name = "FFmpeg" }
)

foreach ($dep in $deps) {
    Info "Installing $($dep.Name)..."
    winget install --id $dep.Id --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) {
        # -1978335189 = "already installed"
        Ok "$($dep.Name) ready"
    } else {
        Warn "$($dep.Name) install returned code $LASTEXITCODE. You may need to install it manually."
    }
}

# Refresh PATH so winget-installed tools are visible in this session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

Write-Host ""

# ── Check Spotify ────────────────────────────────────────────────────────────

$spotifyFound = $false
try {
    $null = Get-AppxPackage -Name "SpotifyAB.SpotifyMusic" -ErrorAction SilentlyContinue
    if ($?) { $spotifyFound = $true }
} catch {}
if (-not $spotifyFound -and (Get-Command spotify -ErrorAction SilentlyContinue)) {
    $spotifyFound = $true
}
if ($spotifyFound) {
    Ok "Spotify is installed"
} else {
    Warn "Spotify not detected. Install it from https://www.spotify.com/download/ or the Microsoft Store."
}

Write-Host ""

# ── Install Python dependencies ──────────────────────────────────────────────

Info "Installing Python dependencies..."
Push-Location $ProjectDir
try {
    & uv sync
    if ($LASTEXITCODE -ne 0) {
        Err "uv sync failed. Please run it manually in $ProjectDir."
        exit 1
    }
    Ok "Python dependencies installed"
} finally {
    Pop-Location
}

Write-Host ""

# ── Create video directory ───────────────────────────────────────────────────

if (-not (Test-Path $VideoDir)) {
    Info "Creating video directory: $VideoDir"
    New-Item -ItemType Directory -Path $VideoDir -Force | Out-Null
    Ok "Video directory created"
} else {
    Ok "Video directory already exists: $VideoDir"
}

# ── Create default config ────────────────────────────────────────────────────

if (-not (Test-Path $ConfigFile)) {
    Info "Creating default config: $ConfigFile"
    New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
    @"
# Directory containing video files named after Spotify tracks
video_dir = "~/Videos/spotify-wallpapers"

# Video file extensions to search for
# video_extensions = [".mp4", ".mkv", ".webm", ".avi"]
"@ | Set-Content -Path $ConfigFile -Encoding UTF8
    Ok "Config created"
} else {
    Ok "Config already exists: $ConfigFile"
}

Write-Host ""

# ── Startup shortcut (optional) ──────────────────────────────────────────────

$answer = Read-Host "Register daemon to run automatically at login? [y/N]"
if ($answer -match '^[Yy]$') {
    $StartupDir = [Environment]::GetFolderPath("Startup")
    $ShortcutPath = Join-Path $StartupDir "spotify-wallpaper.lnk"

    $uvPath = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $uvPath) {
        Warn "Could not find 'uv' on PATH. Skipping startup shortcut."
    } else {
        $wshell = New-Object -ComObject WScript.Shell
        $shortcut = $wshell.CreateShortcut($ShortcutPath)
        $shortcut.TargetPath = $uvPath
        $shortcut.Arguments = "run python main.py"
        $shortcut.WorkingDirectory = $ProjectDir
        $shortcut.WindowStyle = 7  # minimized
        $shortcut.Save()
        Ok "Startup shortcut created: $ShortcutPath"
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host ""
Write-Host "  1. Add video files to: $VideoDir"
Write-Host "     Name them after Spotify track titles, e.g.:"
Write-Host "       Bohemian Rhapsody.mp4"
Write-Host "       Fight Song+-0-22.mp4  (starts at 0:22)"
Write-Host ""
Write-Host "  2. Launch the daemon manually:"
Write-Host "     cd `"$ProjectDir`""
Write-Host "     uv run python main.py"
Write-Host ""
Write-Host "  3. Or reboot if you registered the startup shortcut."
Write-Host ""
