"""Review actions on a song's draft: edits, cover changes, preview and discard."""

import contextlib
import json
import os
import shutil
import signal
import subprocess
import time
from dataclasses import replace
from pathlib import Path

from tunerelay import covers, inbox
from tunerelay.config import Config
from tunerelay.jsondata import JsonObject
from tunerelay.store import REVIEWABLE, Proposal, Song, Store

REQUIRED_TEXT = ("title", "artist", "album", "album_artist")
POSITIVE_INTS = ("track", "track_total", "disc", "disc_total")
MBID_PREFIX = "mbid_"
MBID_KINDS = ("recording", "release", "artist")
LIST_SEPARATOR = ";"


class ReviewError(Exception):
    """An edit or review action that cannot be applied."""


def _whole_number(name: str, value: str) -> int:
    if not value.strip().isdigit():
        raise ReviewError(f"{name} must be a whole number")
    return int(value)


def apply_edits(draft: Proposal, assignments: list[str]) -> Proposal:  # noqa: PLR0912 - one branch per field kind
    """Apply FIELD=VALUE edits. Lists use ';' between items; an empty optional value clears it."""
    texts: dict[str, str] = {}
    numbers: dict[str, int] = {}
    year: int | None = draft.year
    genre: str | None = draft.genre
    compilation = draft.compilation
    artists: list[str] | None = None
    mbids = dict(draft.mbids)
    for assignment in assignments:
        name, separator, value = assignment.partition("=")
        name, value = name.strip(), value.strip()
        if not separator:
            raise ReviewError(f"expected FIELD=VALUE, got: {assignment}")
        if name in REQUIRED_TEXT:
            if not value:
                raise ReviewError(f"{name} cannot be empty")
            texts[name] = value
        elif name in POSITIVE_INTS:
            numbers[name] = max(1, _whole_number(name, value))
        elif name == "year":
            year = _whole_number(name, value) if value else None
        elif name == "genre":
            genre = value or None
        elif name == "compilation":
            if value.lower() not in {"true", "false"}:
                raise ReviewError("compilation must be true or false")
            compilation = value.lower() == "true"
        elif name == "artists":
            artists = [item.strip() for item in value.split(LIST_SEPARATOR) if item.strip()]
        elif name.startswith(MBID_PREFIX) and name.removeprefix(MBID_PREFIX) in MBID_KINDS:
            kind = name.removeprefix(MBID_PREFIX)
            if value:
                mbids[kind] = value
            else:
                mbids.pop(kind, None)
        else:
            raise ReviewError(f"unknown field: {name}")
    if artists is None:
        new_artist = texts.get("artist")
        # A single-artist list follows the main artist, so a rename does not leave a stale credit.
        artists = (
            [new_artist] if new_artist and draft.artists in ([], [draft.artist]) else list(draft.artists)
        )
    return replace(
        draft,
        year=year,
        genre=genre,
        compilation=compilation,
        artists=artists,
        mbids=mbids,
        **texts,
        **numbers,
    )


def custom_cover_path(song: Song) -> Path:
    return Path(song.folder) / f"cover-custom-{time.time_ns()}.jpg"


def thumbnail_cover(song: Song) -> str:
    cover = Path(song.folder) / "cover.jpg"
    if not cover.exists():
        raise ReviewError("this song has no thumbnail")
    return str(cover)


def cover_from_file(song: Song, path: Path) -> str:
    try:
        return str(covers.square_file(path, custom_cover_path(song)))
    except covers.CoverError as error:
        raise ReviewError(str(error)) from error


def cover_from_url(song: Song, url: str) -> str:
    try:
        return str(covers.fetch(url, custom_cover_path(song)))
    except covers.CoverError as error:
        raise ReviewError(str(error)) from error


def preview(cfg: Config, song: Song) -> Path:
    """Play the local audio in the configured player, stopping any earlier preview."""
    audio = inbox.audio_file(Path(song.folder))
    if audio is None:
        raise ReviewError(f"song {song.id} has no local audio")
    pid_file = cfg.home / "preview.json"
    _stop_previous_preview(pid_file)
    process = subprocess.Popen(
        [cfg.tools.player, "--no-video", "--", str(audio)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    started = _start_time(process.pid)
    if started is not None:
        pid_file.write_text(json.dumps({"pid": process.pid, "start": started}))
    return audio


def _start_time(pid: int) -> str | None:
    """When a process started (field 22 of /proc/PID/stat); together with the PID it names one process."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    return stat.rsplit(")", 1)[1].split()[19]


def _stop_previous_preview(pid_file: Path) -> None:
    """Stop the player TuneRelay started last, but only if that PID still names the same process."""
    try:
        record = JsonObject.parse(pid_file.read_text())
    except (OSError, ValueError):
        return
    pid, started = record.integer("pid"), record.text("start")
    if pid is None or started is None or _start_time(pid) != started:
        return
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGTERM)


def history_cover(cfg: Config, song: Song) -> str | None:
    """Keep a small copy of the chosen cover once the local folder goes away."""
    source = song.draft.cover if song.draft else None
    if not source or not Path(source).exists():
        return None
    try:
        return str(covers.square_file(Path(source), cfg.covers / f"{song.id}.jpg", covers.HISTORY_SIZE))
    except covers.CoverError:
        return None


def discard(cfg: Config, store: Store, song_id: int) -> Song:
    song = store.require(song_id, REVIEWABLE)
    discarded = store.discard(song_id, history_cover(cfg, song))
    shutil.rmtree(song.folder, ignore_errors=True)
    return discarded


def check_complete(draft: Proposal | None) -> None:
    if draft is None:
        raise ReviewError("nothing to confirm")
    for name in REQUIRED_TEXT:
        if not getattr(draft, name):
            raise ReviewError(f"{name} cannot be empty")
