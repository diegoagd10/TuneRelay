"""Song state in SQLite (WAL), shared by the CLI, the native host and the daemon.

Every write bumps `meta.version`, which `tunerelay watch` polls to stream changes.
State changes are guarded: a transition only applies if the song is currently in
one of the allowed source states, so concurrent writers cannot skip the lifecycle.
"""

import json
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from tunerelay.jsondata import JsonObject


class State(StrEnum):
    DOWNLOADING = "downloading"
    DOWNLOAD_FAILED = "download_failed"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    IN_TRANSIT = "in_transit"
    SENT = "sent"
    FAILED = "failed"
    CONFLICT = "conflict"
    DISCARDED = "discarded"


IN_FLIGHT = (State.DOWNLOADING, State.QUEUED, State.PROCESSING, State.IN_TRANSIT)
REVIEWABLE = (State.READY_FOR_REVIEW, State.CONFLICT)
HISTORY = (State.SENT, State.DISCARDED, State.FAILED, State.DOWNLOAD_FAILED)
RECAPTURABLE = (State.DISCARDED, State.DOWNLOAD_FAILED)


class StoreError(Exception):
    """A requested change is not possible (unknown song or wrong state)."""


@dataclass(frozen=True)
class Proposal:
    origin: str  # "youtube-default" or "codex"
    title: str
    artist: str
    artists: list[str]
    album: str
    album_artist: str
    track: int
    track_total: int
    disc: int
    disc_total: int
    year: int | None
    genre: str | None
    compilation: bool
    mbids: dict[str, str]
    confidence: float
    sources: list[str]
    cover: str | None  # local path of the square cover image
    cover_url: str | None = None  # where a Codex cover came from

    @classmethod
    def from_json(cls, data: JsonObject) -> "Proposal":
        return cls(
            origin=data.text("origin") or "codex",
            title=data.text("title") or "",
            artist=data.text("artist") or "",
            artists=data.texts("artists"),
            album=data.text("album") or "",
            album_artist=data.text("album_artist") or "",
            track=data.integer("track") or 1,
            track_total=data.integer("track_total") or 1,
            disc=data.integer("disc") or 1,
            disc_total=data.integer("disc_total") or 1,
            year=data.integer("year"),
            genre=data.text("genre"),
            compilation=data.flag("compilation") or False,
            mbids=data.text_map("mbids"),
            confidence=data.number("confidence") or 0.0,
            sources=data.texts("sources"),
            cover=data.text("cover"),
            cover_url=data.text("cover_url"),
        )


@dataclass(frozen=True)
class YouTubeInfo:
    title: str
    channel: str
    upload_date: str
    duration: int
    description: str
    chapters: list[str] = field(default_factory=list[str])

    @classmethod
    def from_json(cls, data: JsonObject) -> "YouTubeInfo":
        return cls(
            title=data.text("title") or "",
            channel=data.text("channel") or data.text("uploader") or "",
            upload_date=data.text("upload_date") or "",
            duration=data.integer("duration") or 0,
            description=data.text("description") or "",
            # yt-dlp lists chapters as objects; the store keeps just their titles.
            chapters=[c.text("title") or "" for c in data.objects("chapters")] + data.texts("chapters"),
        )


@dataclass(frozen=True)
class Song:
    id: int
    video_id: str
    url: str
    state: State
    folder: str
    youtube: YouTubeInfo | None
    proposals: list[Proposal]
    selected: int | None
    draft: Proposal | None
    progress: int | None
    attempts: int
    error: str | None
    remote_path: str | None
    history_cover: str | None
    overwrite: bool
    worker_pid: int | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CaptureResult:
    accepted: bool
    song: Song  # the existing song when the capture is a duplicate


SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    state TEXT NOT NULL,
    folder TEXT NOT NULL,
    youtube TEXT,
    proposals TEXT NOT NULL DEFAULT '[]',
    selected INTEGER,
    draft TEXT,
    progress INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    remote_path TEXT,
    history_cover TEXT,
    overwrite INTEGER NOT NULL DEFAULT 0,
    worker_pid INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL);
INSERT OR IGNORE INTO meta (id, version) VALUES (1, 0);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _marks(states: tuple[State, ...]) -> str:
    return ",".join("?" for _ in states)


def _proposal_json(proposal: Proposal) -> str:
    return json.dumps(asdict(proposal))


def _song(row: sqlite3.Row) -> Song:
    youtube = row["youtube"]
    draft = row["draft"]
    return Song(
        id=row["id"],
        video_id=row["video_id"],
        url=row["url"],
        state=State(row["state"]),
        folder=row["folder"],
        youtube=YouTubeInfo.from_json(JsonObject.parse(youtube)) if youtube else None,
        proposals=[Proposal.from_json(item) for item in JsonObject.parse_list(row["proposals"])],
        selected=row["selected"],
        draft=Proposal.from_json(JsonObject.parse(draft)) if draft else None,
        progress=row["progress"],
        attempts=row["attempts"],
        error=row["error"],
        remote_path=row["remote_path"],
        history_cover=row["history_cover"],
        overwrite=bool(row["overwrite"]),
        worker_pid=row["worker_pid"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _worker_alive(song: Song) -> bool:
    """Whether the detached download worker of a `downloading` song is still running."""
    if song.worker_pid is None:
        return False
    try:
        os.kill(song.worker_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _haystack(song: Song) -> str:
    parts = [song.video_id, song.url, song.remote_path or ""]
    if song.draft:
        parts += [
            song.draft.title,
            song.draft.artist,
            song.draft.album,
            song.draft.album_artist,
            *song.draft.artists,
        ]
    if song.youtube:
        parts += [song.youtube.title, song.youtube.channel]
    return " ".join(parts).casefold()


class Store:
    def __init__(self, path: Path) -> None:
        self._db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    @contextmanager
    def _write(self) -> Generator[sqlite3.Connection]:
        """One IMMEDIATE transaction that also bumps the change version."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield self._db
            self._db.execute("UPDATE meta SET version = version + 1")
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def _find(self, song_id: int) -> Song:
        row = self._db.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
        if row is None:
            raise StoreError(f"no song with id {song_id}")
        return _song(row)

    def require(self, song_id: int, allowed: tuple[State, ...]) -> Song:
        song = self._find(song_id)
        if song.state not in allowed:
            expected = ", ".join(allowed)
            raise StoreError(f"song {song_id} is {song.state}; expected {expected}")
        return song

    # Reads

    def get(self, song_id: int) -> Song:
        return self._find(song_id)

    def version(self) -> int:
        return int(self._db.execute("SELECT version FROM meta").fetchone()[0])

    def songs(self, states: tuple[State, ...]) -> list[Song]:
        rows = self._db.execute(
            f"SELECT * FROM songs WHERE state IN ({_marks(states)}) ORDER BY id",  # noqa: S608 - only placeholders
            states,
        ).fetchall()
        return [_song(row) for row in rows]

    def all_songs(self) -> list[Song]:
        return [_song(row) for row in self._db.execute("SELECT * FROM songs ORDER BY id").fetchall()]

    def history(self, query: str, state: State | None) -> list[Song]:
        """Songs in a final state, newest first, matching `query` in their metadata or YouTube data."""
        states = (state,) if state else HISTORY
        songs = sorted(self.songs(states), key=lambda song: (song.updated_at, song.id), reverse=True)
        needle = query.strip().casefold()
        return [song for song in songs if needle in _haystack(song)]

    def find_video(self, video_id: str) -> Song | None:
        row = self._db.execute("SELECT * FROM songs WHERE video_id = ?", (video_id,)).fetchone()
        return _song(row) if row else None

    # Capture

    def claim_capture(self, video_id: str, url: str, folder: Path) -> CaptureResult:
        """Register a new download unless the video is already known (and not discarded or failed)."""
        with self._write() as db:
            existing = self.find_video(video_id)
            stale = (
                existing is not None and existing.state == State.DOWNLOADING and not _worker_alive(existing)
            )
            if existing is not None and existing.state not in RECAPTURABLE and not stale:
                return CaptureResult(accepted=False, song=existing)
            now = _now()
            if existing is None:
                cursor = db.execute(
                    "INSERT INTO songs (video_id, url, state, folder, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (video_id, url, State.DOWNLOADING, str(folder), now, now),
                )
                song_id = cursor.lastrowid or 0
            else:
                song_id = existing.id
                db.execute(
                    "UPDATE songs SET url = ?, state = ?, folder = ?, youtube = NULL, proposals = '[]',"
                    " selected = NULL, draft = NULL, progress = NULL, attempts = 0, error = NULL,"
                    " worker_pid = NULL, remote_path = NULL, history_cover = NULL, overwrite = 0,"
                    " created_at = ?, updated_at = ?"
                    " WHERE id = ?",
                    (url, State.DOWNLOADING, str(folder), now, now, song_id),
                )
        return CaptureResult(accepted=True, song=self._find(song_id))

    def set_worker(self, song_id: int, pid: int) -> None:
        with self._write() as db:
            db.execute("UPDATE songs SET worker_pid = ? WHERE id = ?", (pid, song_id))

    def set_progress(self, song_id: int, percent: int) -> None:
        with self._write() as db:
            db.execute(
                "UPDATE songs SET progress = ? WHERE id = ? AND state = ?",
                (percent, song_id, State.DOWNLOADING),
            )

    def mark_downloaded(self, song_id: int, youtube: YouTubeInfo) -> Song:
        with self._write() as db:
            self.require(song_id, (State.DOWNLOADING,))
            db.execute(
                "UPDATE songs SET state = ?, youtube = ?, progress = 100, updated_at = ? WHERE id = ?",
                (State.QUEUED, json.dumps(asdict(youtube)), _now(), song_id),
            )
        return self._find(song_id)

    def mark_download_failed(self, song_id: int, error: str) -> Song:
        with self._write() as db:
            self.require(song_id, (State.DOWNLOADING,))
            db.execute(
                "UPDATE songs SET state = ?, error = ?, updated_at = ? WHERE id = ?",
                (State.DOWNLOAD_FAILED, error, _now(), song_id),
            )
        return self._find(song_id)

    def adopt(self, video_id: str, url: str, folder: Path, youtube: YouTubeInfo) -> Song:
        """Queue a folder dropped into the inbox by hand."""
        result = self.claim_capture(video_id, url, folder)
        return self.mark_downloaded(result.song.id, youtube) if result.accepted else result.song

    # Processing

    def recover(self) -> None:
        """After a restart, songs interrupted mid-processing go back to the queue, and downloads
        whose worker died are marked failed (so they can be captured again)."""
        dead = [song.id for song in self.songs((State.DOWNLOADING,)) if not _worker_alive(song)]
        with self._write() as db:
            db.execute(
                "UPDATE songs SET state = ?, updated_at = ? WHERE state = ?",
                (State.QUEUED, _now(), State.PROCESSING),
            )
            for song_id in dead:
                db.execute(
                    "UPDATE songs SET state = ?, error = ?, updated_at = ? WHERE id = ? AND state = ?",
                    (State.DOWNLOAD_FAILED, "download interrupted", _now(), song_id, State.DOWNLOADING),
                )

    def start_processing(self) -> Song | None:
        with self._write() as db:
            row = db.execute(
                "SELECT id FROM songs WHERE state = ? ORDER BY updated_at, id LIMIT 1", (State.QUEUED,)
            ).fetchone()
            if row is None:
                return None
            db.execute(
                "UPDATE songs SET state = ?, updated_at = ? WHERE id = ?",
                (State.PROCESSING, _now(), row["id"]),
            )
        return self._find(row["id"])

    def finish_processing(self, song_id: int, proposals: list[Proposal]) -> Song:
        """Store the ordered proposals and preselect the first one."""
        with self._write() as db:
            self.require(song_id, (State.PROCESSING,))
            db.execute(
                "UPDATE songs SET state = ?, proposals = ?, selected = 0, draft = ?, updated_at = ?"
                " WHERE id = ?",
                (
                    State.READY_FOR_REVIEW,
                    json.dumps([asdict(p) for p in proposals]),
                    _proposal_json(proposals[0]),
                    _now(),
                    song_id,
                ),
            )
        return self._find(song_id)

    # Review

    def select(self, song_id: int, index: int) -> Song:
        with self._write() as db:
            song = self.require(song_id, REVIEWABLE)
            if not 0 <= index < len(song.proposals):
                raise StoreError(f"song {song_id} has no proposal {index}")
            db.execute(
                "UPDATE songs SET selected = ?, draft = ?, updated_at = ? WHERE id = ?",
                (index, _proposal_json(song.proposals[index]), _now(), song_id),
            )
        return self._find(song_id)

    def save_draft(self, song_id: int, draft: Proposal) -> Song:
        with self._write() as db:
            self.require(song_id, REVIEWABLE)
            db.execute(
                "UPDATE songs SET draft = ?, updated_at = ? WHERE id = ?",
                (_proposal_json(draft), _now(), song_id),
            )
        return self._find(song_id)

    def confirm(self, song_id: int) -> Song:
        with self._write() as db:
            self.require(song_id, REVIEWABLE)
            db.execute(
                "UPDATE songs SET state = ?, attempts = 0, error = NULL, overwrite = 0, updated_at = ?"
                " WHERE id = ?",
                (State.IN_TRANSIT, _now(), song_id),
            )
        return self._find(song_id)

    def replace(self, song_id: int) -> Song:
        with self._write() as db:
            self.require(song_id, (State.CONFLICT,))
            db.execute(
                "UPDATE songs SET state = ?, attempts = 0, error = NULL, overwrite = 1, updated_at = ?"
                " WHERE id = ?",
                (State.IN_TRANSIT, _now(), song_id),
            )
        return self._find(song_id)

    def discard(self, song_id: int, history_cover: str | None) -> Song:
        with self._write() as db:
            self.require(song_id, REVIEWABLE)
            db.execute(
                "UPDATE songs SET state = ?, history_cover = ?, updated_at = ? WHERE id = ?",
                (State.DISCARDED, history_cover, _now(), song_id),
            )
        return self._find(song_id)

    def retry(self, song_id: int) -> Song:
        with self._write() as db:
            self.require(song_id, (State.FAILED,))
            db.execute(
                "UPDATE songs SET state = ?, attempts = 0, error = NULL, updated_at = ? WHERE id = ?",
                (State.IN_TRANSIT, _now(), song_id),
            )
        return self._find(song_id)

    # Delivery

    def next_in_transit(self) -> Song | None:
        row = self._db.execute(
            "SELECT * FROM songs WHERE state = ? ORDER BY updated_at, id LIMIT 1", (State.IN_TRANSIT,)
        ).fetchone()
        return _song(row) if row else None

    def record_failure(self, song_id: int, error: str, max_attempts: int) -> Song:
        """Count a failed delivery attempt; the last allowed one marks the song failed."""
        with self._write() as db:
            song = self.require(song_id, (State.IN_TRANSIT,))
            attempts = song.attempts + 1
            state = State.FAILED if attempts >= max_attempts else State.IN_TRANSIT
            db.execute(
                "UPDATE songs SET state = ?, attempts = ?, error = ?, updated_at = ? WHERE id = ?",
                (state, attempts, error, _now(), song_id),
            )
        return self._find(song_id)

    def mark_conflict(self, song_id: int, remote_path: str) -> Song:
        with self._write() as db:
            self.require(song_id, (State.IN_TRANSIT,))
            db.execute(
                "UPDATE songs SET state = ?, remote_path = ?, error = ?, updated_at = ? WHERE id = ?",
                (State.CONFLICT, remote_path, "already exists in Navidrome", _now(), song_id),
            )
        return self._find(song_id)

    def mark_sent(self, song_id: int, remote_path: str, history_cover: str | None) -> Song:
        with self._write() as db:
            self.require(song_id, (State.IN_TRANSIT,))
            db.execute(
                "UPDATE songs SET state = ?, remote_path = ?, history_cover = ?, error = NULL, updated_at = ?"
                " WHERE id = ?",
                (State.SENT, remote_path, history_cover, _now(), song_id),
            )
        return self._find(song_id)
