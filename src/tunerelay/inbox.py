"""Song folders in `~/.tunerelay/inbox/<id>/` and the `ready` marker that gates processing."""

from pathlib import Path

from tunerelay.jsondata import JsonObject
from tunerelay.store import YouTubeInfo

READY = "ready"
THUMBNAIL_SUFFIXES = (".jpg", ".jpeg", ".webp", ".png")


def mark_ready(folder: Path) -> None:
    (folder / READY).touch()


def is_ready(folder: Path) -> bool:
    return (folder / READY).exists()


def audio_file(folder: Path) -> Path | None:
    files = sorted(folder.glob("*.m4a"))
    return files[0] if files else None


def thumbnail_file(folder: Path) -> Path | None:
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in THUMBNAIL_SUFFIXES and not path.name.startswith("cover"):
            return path
    return None


def read_info(folder: Path, fallback_title: str) -> YouTubeInfo:
    """YouTube info from the folder's `*.info.json`, or a bare title for a manual drop without one."""
    for path in sorted(folder.glob("*.info.json")):
        try:
            return YouTubeInfo.from_json(JsonObject.parse(path.read_text()))
        except ValueError:
            continue
    return YouTubeInfo(title=fallback_title, channel="", upload_date="", duration=0, description="")
