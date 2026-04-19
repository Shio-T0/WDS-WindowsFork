import os
import tomllib
from pathlib import Path
from dataclasses import dataclass, field

# Windows: use %APPDATA%, fall back to a home-relative path
APPDATA = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
CONFIG_DIR = APPDATA / "spotify-wallpaper"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class Config:
    video_dir: str = "~/Videos/spotify-wallpapers"
    video_extensions: list[str] = field(
        default_factory=lambda: [".mp4", ".mkv", ".webm", ".avi"]
    )

    @classmethod
    def load(cls) -> "Config":
        if not CONFIG_FILE.exists():
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(
                '# Directory containing video files named after Spotify tracks\n'
                'video_dir = "~/Videos/spotify-wallpapers"\n\n'
                '# Video file extensions to search for\n'
                '# video_extensions = [".mp4", ".mkv", ".webm", ".avi"]\n'
            )
            raise SystemExit(
                f"Config created at {CONFIG_FILE}\n"
                f"Edit video_dir and restart the daemon."
            )

        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)

        cfg = cls()
        cfg.video_dir = data.get("video_dir", cfg.video_dir)
        cfg.video_extensions = data.get("video_extensions", cfg.video_extensions)

        return cfg

    @property
    def video_path(self) -> Path:
        return Path(self.video_dir).expanduser()
