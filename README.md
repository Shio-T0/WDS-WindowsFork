# WDS-Windows - Wallpaper Display for Spotify

A Windows daemon that detects the currently playing Spotify track, finds a matching video file, and plays it as an animated wallpaper using [Lively Wallpaper](https://www.rocksdanister.com/lively/). It syncs playback state and volume with Spotify.

This is a Windows port of the original [Linux version](https://github.com/Shio-T0/WDS-Wallpaper-Display-for-Spotify).

## Features

- Detects the currently playing Spotify track via Windows SMTC (System Media Transport Controls)
- Plays a matching video as your desktop wallpaper through Lively Wallpaper
- Mutes Spotify audio and plays the video's audio instead, with volume synced
- Pauses/resumes the wallpaper video when you pause/resume Spotify
- Supports filename time offsets (e.g. `song+-0-22.mp4` starts the video at 0:22)
- Handles Spotify closing and reopening gracefully

> **Note:** This Windows version does not include the color scheme matching or RGB LED sync features of the Linux version. It also has limited manual-seek support (depends on Lively's CLI capabilities).

## Demo

In [here](https://github.com/Shio-T0/WDS-Wallpaper-Display-for-Spotify)

## Dependencies

| Dependency | Purpose |
|---|---|
| Windows 10 (1809+) / Windows 11 | SMTC required for Spotify detection |
| [Python](https://www.python.org/) >= 3.11 | Runtime |
| [uv](https://github.com/astral-sh/uv) | Python package manager |
| [Spotify](https://www.spotify.com/) | Music player (must expose SMTC — Microsoft Store or regular build) |
| [Lively Wallpaper](https://www.rocksdanister.com/lively/) | Video wallpaper backend |
| [FFmpeg](https://ffmpeg.org/) | Available on PATH |
| `winsdk`, `pycaw`, `psutil`, `Pillow` | Python packages (installed automatically) |

## Installation

### Automatic (recommended)

Open PowerShell (a regular one — not as admin) and run:

```powershell
git clone https://github.com/Shio-T0/WDS-WindowsFork
cd WDS-WindowsFork
powershell -ExecutionPolicy Bypass -File install.ps1
```

The install script will:
1. Install Python 3.11, uv, Lively Wallpaper, and FFmpeg via `winget`
2. Install Python dependencies via `uv`
3. Create the video directory at `%USERPROFILE%\Videos\spotify-wallpapers`
4. Generate a default config at `%APPDATA%\spotify-wallpaper\config.toml`
5. Optionally register a Startup shortcut so the daemon runs automatically at login

No administrator privileges required.

### Manual

1. Install dependencies via winget:

```powershell
winget install Python.Python.3.11
winget install astral-sh.uv
winget install rocksdanister.LivelyWallpaper
winget install Gyan.FFmpeg
```

2. Install Spotify from https://www.spotify.com/download/ or the Microsoft Store.

3. Clone and sync:

```powershell
git clone https://github.com/Shio-T0/WDS-WindowsFork
cd WDS-WindowsFork
uv sync
```

4. Create the video directory:

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE\Videos\spotify-wallpapers" -Force
```

5. Run the daemon:

```powershell
uv run python main.py
```

On first run, a config file is generated at `%APPDATA%\spotify-wallpaper\config.toml`. Edit `video_dir` if needed, then run again.

## Usage

### Adding videos

Place video files in `%USERPROFILE%\Videos\spotify-wallpapers\`. The filename must match the Spotify track title (case-insensitive):

```
Videos\spotify-wallpapers\
  Bohemian Rhapsody.mp4
  Stairway to Heaven.mkv
  Fight Song+-0-22.mp4         (video starts at 0:22)
```

### Filename time offsets

If a video should start partway through (e.g. to skip an intro), add `+-M-SS` or `+-SS` before the extension:

> Note: Windows filesystems don't allow `:` in filenames, so the separator is a dash in the filename form (`+-0-22` means 0:22).

```
Track Name+-0-22.mp4   # video starts at 22 seconds
Track Name+-1-30.mp4   # video starts at 1 minute 30 seconds
Track Name+-5.mp4      # video starts at 5 seconds
```

### Running

Manually:

```powershell
cd <repo-path>
uv run python main.py
```

Press `Ctrl+C` to stop.

If you registered the startup shortcut during install, the daemon runs automatically when you log in.

### Configuration

Edit `%APPDATA%\spotify-wallpaper\config.toml`:

```toml
# Directory containing video files named after Spotify tracks
video_dir = "~/Videos/spotify-wallpapers"

# Video file extensions to search for
# video_extensions = [".mp4", ".mkv", ".webm", ".avi"]
```

## How it works

1. The daemon connects to Windows SMTC and finds a media session whose source contains "Spotify"
2. It polls the session for track title and playback status every 500ms
3. When a track plays, it searches the video directory for a matching file
4. If found, it tells Lively Wallpaper to set the video as the desktop background, mutes Spotify via `pycaw`, and sets Lively's volume to ~70% of Spotify's previous level
5. When the track pauses, the wallpaper pauses (Lively permitting)
6. When the track changes to one with no matching video, the wallpaper is removed and Spotify is unmuted
7. If Spotify closes, the daemon cleans up and waits for it to reappear

## Known limitations

- **Precise seek syncing** is not supported. The Linux version uses mpvpaper's mpv IPC socket to set the video position on Spotify seeks; Lively Wallpaper's CLI exposes no equivalent. Pause/resume and initial offsets still work, but manually seeking in Spotify won't move the video.
- **Initial offset** (`+-M-SS`) is passed via Lively's `setwpproperty CurrentTime` which depends on the Lively plugin's support for it.

## License

MIT
