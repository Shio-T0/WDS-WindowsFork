import asyncio
import logging
import re
import signal
import subprocess
from pathlib import Path

import psutil
from pycaw.pycaw import AudioUtilities
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)

from config import Config

log = logging.getLogger("spotify-wallpaper")


def _parse_offset(stem: str) -> tuple[str, float]:
    """Parse 'title+-M:SS' or 'title+-SS' from a filename stem.
    Returns (title_part, offset_seconds)."""
    match = re.search(r"\+\-(\d+):(\d+(?:\.\d+)?)$", stem)
    if match:
        minutes, secs = int(match.group(1)), float(match.group(2))
        title_part = stem[: match.start()]
        return title_part, minutes * 60 + secs
    match = re.search(r"\+\-(\d+(?:\.\d+)?)$", stem)
    if match:
        title_part = stem[: match.start()]
        return title_part, float(match.group(1))
    return stem, 0.0


def find_video(title: str, config: Config) -> tuple[Path | None, float]:
    """Find a video matching the track title. Returns (path, offset_seconds).
    Filenames can be 'title.ext' or 'title+-M:SS.ext'."""
    video_dir = config.video_path
    if not video_dir.is_dir():
        return None, 0.0
    title_clean = re.sub(r'[<>:"/\\|?*]', "", title).strip()
    title_lower = title_clean.lower()
    if not title_lower:
        return None, 0.0
    for path in video_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in config.video_extensions:
            continue
        name_part, offset = _parse_offset(path.stem)
        if name_part.lower() == title_lower:
            return path, offset
    return None, 0.0


class SpotifyAudio:
    """Control Spotify's audio session via Windows Core Audio API (pycaw)."""

    @staticmethod
    def _get_session():
        for session in AudioUtilities.GetAllSessions():
            if not session.Process:
                continue
            name = (session.Process.name() or "").lower()
            if "spotify" in name:
                return session
        return None

    @classmethod
    def mute(cls) -> None:
        session = cls._get_session()
        if session:
            log.info("Muting Spotify")
            session.SimpleAudioVolume.SetMute(1, None)

    @classmethod
    def unmute(cls) -> None:
        session = cls._get_session()
        if session:
            log.info("Unmuting Spotify")
            session.SimpleAudioVolume.SetMute(0, None)

    @classmethod
    def get_volume_percent(cls) -> int | None:
        session = cls._get_session()
        if session:
            return int(session.SimpleAudioVolume.GetMasterVolume() * 100)
        return None


class LivelyWallpaper:
    """Wrapper around Lively Wallpaper's CLI (livelycu.exe).

    Note: Lively's CLI has limited IPC compared to mpvpaper. This backend
    supports: start, stop, and best-effort pause/resume. Precise seeking is
    not supported.
    """

    def __init__(self):
        self.current_video: Path | None = None
        self.paused: bool = False
        self._exe = self._find_cli()

    def _find_cli(self) -> str:
        """Locate livelycu.exe. Returns 'livelycu' if on PATH, else full path."""
        candidates = [
            "livelycu",
            r"C:\Program Files\Lively Wallpaper\livelycu.exe",
            r"C:\Program Files (x86)\Lively Wallpaper\livelycu.exe",
            str(Path.home() / "AppData" / "Local" / "Programs" / "Lively Wallpaper" / "livelycu.exe"),
        ]
        for c in candidates:
            if c == "livelycu":
                try:
                    subprocess.run([c, "--help"], capture_output=True, timeout=3)
                    return c
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
            elif Path(c).exists():
                return c
        return "livelycu"  # fallback, will fail loudly if not installed

    def _run(self, args: list[str]) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(
                [self._exe, *args],
                capture_output=True, text=True, timeout=15,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            log.warning("livelycu failed: %s", e)
            return None

    def start(self, video_path: Path, start_pos: float = 0.0) -> None:
        if self.current_video == video_path and not self.paused:
            return
        log.info("Setting wallpaper: %s (start_pos=%.1fs)", video_path.name, start_pos)
        self._run(["setwp", "--file", str(video_path)])
        self.current_video = video_path
        self.paused = False
        # Best-effort: seek to offset via property (depends on Lively plugin)
        if start_pos > 0:
            self._run(["setwpproperty", "--property", f"CurrentTime={start_pos}"])

    def pause(self) -> None:
        if self.current_video and not self.paused:
            log.info("Pausing wallpaper")
            self._run(["setwpplay", "--play", "0"])
            self.paused = True

    def resume(self) -> None:
        if self.current_video and self.paused:
            log.info("Resuming wallpaper")
            self._run(["setwpplay", "--play", "1"])
            self.paused = False

    def set_volume(self, volume_percent: int) -> None:
        vol = max(0, min(100, volume_percent))
        log.info("Setting wallpaper volume to %d%%", vol)
        self._run(["setwpvolume", "--volume", str(vol)])

    def stop(self) -> None:
        if self.current_video:
            log.info("Closing wallpaper")
            self._run(["closewp"])
        self.current_video = None
        self.paused = False


class Daemon:
    def __init__(self, config: Config):
        self.config = config
        self.wallpaper = LivelyWallpaper()
        self.current_track: str | None = None
        self.is_playing: bool = False
        self.video_active: bool = False
        self.video_offset: float = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None

    def _reconcile_soon(self) -> None:
        """Schedule a reconciliation on the main loop from a signal callback."""
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._reconcile(), self._loop)

    async def _reconcile(self) -> None:
        if not self.is_playing or not self.current_track:
            if self.video_active:
                self.wallpaper.pause()
            return

        video, offset = find_video(self.current_track, self.config)
        if video:
            is_new_video = not self.video_active or self.wallpaper.current_video != video
            self.video_offset = offset
            self.wallpaper.start(video, start_pos=offset)
            SpotifyAudio.mute()
            self.video_active = True
            # Sync volume after a short delay
            self._loop.call_later(1.0, self._sync_initial_volume)
        else:
            if self.video_active:
                self.wallpaper.stop()
                SpotifyAudio.unmute()
                self.video_active = False

    def _sync_initial_volume(self) -> None:
        vol = SpotifyAudio.get_volume_percent()
        if vol is not None:
            self.wallpaper.set_volume(int(vol * 0.7))  # scale to match perceived loudness

    def cleanup(self) -> None:
        self.wallpaper.stop()
        if self.video_active:
            SpotifyAudio.unmute()
            self.video_active = False


class SpotifyWatcher:
    """Watches Spotify playback via Windows SMTC.

    Calls back into Daemon on track/status/position changes.
    """

    def __init__(self, daemon: Daemon):
        self.daemon = daemon
        self.manager: MediaManager | None = None
        self.session = None
        self._last_title: str | None = None
        self._last_status: PlaybackStatus | None = None

    async def _ensure_manager(self) -> None:
        if not self.manager:
            self.manager = await MediaManager.request_async()

    @staticmethod
    def _is_spotify_session(session) -> bool:
        aumid = (session.source_app_user_model_id or "").lower()
        return "spotify" in aumid

    async def find_spotify_session(self):
        """Return the Spotify SMTC session or None."""
        await self._ensure_manager()
        sessions = self.manager.get_sessions()
        for i in range(sessions.size):
            s = sessions.get_at(i)
            if self._is_spotify_session(s):
                return s
        return None

    @staticmethod
    def _spotify_process_running() -> bool:
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").lower()
            if "spotify" in n:
                return True
        return False

    async def _refresh_state(self) -> None:
        """Pull current media + playback info from the session into the daemon."""
        if not self.session:
            return
        try:
            props = await self.session.try_get_media_properties_async()
            title = (props.title or "").strip() if props else ""
        except Exception as e:
            log.warning("get_media_properties failed: %s", e)
            title = ""

        try:
            info = self.session.get_playback_info()
            status = info.playback_status if info else None
        except Exception as e:
            log.warning("get_playback_info failed: %s", e)
            status = None

        track_changed = title and title != self._last_title
        is_playing = status == PlaybackStatus.PLAYING
        status_changed = status != self._last_status

        self._last_title = title or self._last_title
        self._last_status = status

        if track_changed:
            self.daemon.current_track = title
            log.info("Track changed: %s", title)
        if status_changed:
            self.daemon.is_playing = is_playing
            log.info("Playback status: %s", status.name if status else "Unknown")

        if track_changed or status_changed:
            await self.daemon._reconcile()

    async def run(self) -> None:
        """Main loop: wait for Spotify, poll state, exit when Spotify disappears."""
        log.info("Waiting for Spotify to start...")
        while True:
            session = await self.find_spotify_session()
            if session:
                self.session = session
                log.info("Spotify detected via SMTC")
                break
            await asyncio.sleep(2)

        # SMTC event callbacks can't reliably dispatch to asyncio from a
        # background thread, so we poll every 500ms. Cheap and robust.
        try:
            while True:
                if not self._spotify_process_running():
                    log.info("Spotify process exited")
                    self.daemon.cleanup()
                    return
                await self._refresh_state()
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = Config.load()
    log.info("Video directory: %s", config.video_path)
    log.info("Video extensions: %s", config.video_extensions)

    stop = asyncio.Event()
    loop = asyncio.get_event_loop()

    # Windows: SIGINT via Ctrl+C works; SIGTERM does not — use signal handler
    # where supported, otherwise rely on KeyboardInterrupt.
    try:
        loop.add_signal_handler(signal.SIGINT, stop.set)
    except NotImplementedError:
        pass

    try:
        while not stop.is_set():
            daemon = Daemon(config)
            daemon._loop = loop
            watcher = SpotifyWatcher(daemon)

            session_task = asyncio.create_task(watcher.run())
            stop_task = asyncio.create_task(stop.wait())

            done, _ = await asyncio.wait(
                {session_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )

            if stop_task in done:
                session_task.cancel()
                try:
                    await session_task
                except asyncio.CancelledError:
                    pass
                daemon.cleanup()
                break

            daemon.cleanup()
            log.info("Will reconnect when Spotify starts again...")
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Daemon stopped.")


def main_sync() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main_sync()
