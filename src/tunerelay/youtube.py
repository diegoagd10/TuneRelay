"""YouTube URL normalisation and the yt-dlp download into an inbox folder."""

import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tunerelay.config import Config

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"}
PATH_PREFIXES = ("/shorts/", "/live/", "/embed/", "/v/")
PROGRESS = re.compile(r"TUNERELAY_PROGRESS\s+(\d+)")
AUDIO_NAME = "audio"


class InvalidUrlError(ValueError):
    """The URL does not point at a single YouTube video."""


def normalize_url(url: str) -> str:
    """Return the video ID of a YouTube / YouTube Music URL, ignoring playlist and other parameters."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    candidate = ""
    if parsed.scheme in {"http", "https"}:
        if host == "youtu.be":
            candidate = parsed.path.strip("/").split("/")[0]
        elif host in HOSTS:
            if parsed.path == "/watch":
                candidate = parse_qs(parsed.query).get("v", [""])[0]
            else:
                for prefix in PATH_PREFIXES:
                    if parsed.path.startswith(prefix):
                        candidate = parsed.path.removeprefix(prefix).split("/")[0]
    if not VIDEO_ID.match(candidate):
        raise InvalidUrlError(f"not a YouTube video URL: {url}")
    return candidate


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def download(cfg: Config, video_id: str, folder: Path, on_progress: Callable[[int], None]) -> str | None:
    """Download best M4A audio (no re-encoding), info JSON and thumbnail. Returns an error message or None."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return f"cannot create the download folder {folder}: {error.strerror or error}"
    command = [
        cfg.tools.ytdlp,
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--progress",
        "--newline",
        "--progress-template",
        "download:TUNERELAY_PROGRESS %(progress._percent_str)s",
        "-f",
        "bestaudio[ext=m4a]",
        "--write-info-json",
        "--write-thumbnail",
        "-o",
        str(folder / f"{AUDIO_NAME}.%(ext)s"),
        "--",
        canonical_url(video_id),
    ]
    try:
        with subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL
        ) as process:
            assert process.stdout is not None  # noqa: S101 - guaranteed by stdout=PIPE
            last = -1
            for line in process.stdout:
                match = PROGRESS.search(line)
                if match and int(match.group(1)) != last:
                    last = int(match.group(1))
                    on_progress(last)
            stderr = process.stderr.read() if process.stderr else ""
    except OSError as error:
        return f"cannot run yt-dlp ({cfg.tools.ytdlp}): {error}"
    if process.returncode != 0:
        lines = [line for line in stderr.splitlines() if line.strip()]
        return lines[-1] if lines else f"yt-dlp exited with {process.returncode}"
    if not (folder / f"{AUDIO_NAME}.m4a").exists():
        return "yt-dlp did not produce an M4A file"
    return None
