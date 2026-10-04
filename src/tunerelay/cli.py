"""`tunerelay`: the CLI used by the Omarchy plugin and from a terminal. Every command prints JSON."""

import json
import sys
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from tunerelay import config, review
from tunerelay.config import Config, ConfigError
from tunerelay.daemon import run as run_daemon
from tunerelay.store import IN_FLIGHT, REVIEWABLE, Proposal, Song, State, Store, StoreError

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

WATCH_POLL = 0.3

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Capture YouTube songs into Navidrome.")


@app.callback()
def root() -> None:
    """TuneRelay: capture YouTube songs into Navidrome with AI-assisted metadata review."""


@dataclass(frozen=True)
class ErrorOutput:
    error: str


@dataclass(frozen=True)
class SongSummary:
    """One line of the Review / Queue / History lists."""

    id: int
    video_id: str
    url: str
    state: str
    title: str
    artist: str
    album: str
    youtube_title: str
    channel: str
    cover: str | None
    progress: int | None
    attempts: int
    error: str | None
    remote_path: str | None
    updated_at: str

    @classmethod
    def of(cls, song: Song) -> "SongSummary":
        draft = song.draft
        return cls(
            id=song.id,
            video_id=song.video_id,
            url=song.url,
            state=song.state,
            title=draft.title if draft else "",
            artist=draft.artist if draft else "",
            album=draft.album if draft else "",
            youtube_title=song.youtube.title if song.youtube else "",
            channel=song.youtube.channel if song.youtube else "",
            cover=song.history_cover or (draft.cover if draft else None),
            progress=song.progress,
            attempts=song.attempts,
            error=song.error,
            remote_path=song.remote_path,
            updated_at=song.updated_at,
        )


@dataclass(frozen=True)
class StatusOutput:
    version: int
    review: int
    busy: bool
    max_attempts: int
    counts: dict[str, int]
    review_songs: list[SongSummary]
    queue: list[SongSummary]


@dataclass(frozen=True)
class PreviewOutput:
    id: int
    audio: str


@dataclass(frozen=True)
class SongList:
    songs: list[SongSummary]


class CommandError(Exception):
    """A user-facing failure, printed as {"error": ...} with a non-zero exit code."""


def emit(data: str) -> None:
    sys.stdout.write(data + "\n")
    sys.stdout.flush()


def to_json(value: "DataclassInstance") -> str:
    return json.dumps(asdict(value), ensure_ascii=False)


@contextmanager
def session() -> Generator[tuple[Config, Store]]:
    cfg = config.load()
    store = Store(cfg.database)
    try:
        yield cfg, store
    except (StoreError, ConfigError, CommandError, review.ReviewError) as error:
        emit(to_json(ErrorOutput(error=str(error))))
        raise typer.Exit(1) from error
    finally:
        store.close()


def status_of(cfg: Config, store: Store) -> StatusOutput:
    version = store.version()
    songs = store.all_songs()
    counts = {state.value: 0 for state in State}
    for song in songs:
        counts[song.state] += 1
    queue = [SongSummary.of(song) for song in songs if song.state in IN_FLIGHT]
    return StatusOutput(
        version=version,
        review=sum(counts[state] for state in REVIEWABLE),
        busy=bool(queue),
        max_attempts=cfg.delivery.max_attempts,
        counts=counts,
        review_songs=[SongSummary.of(song) for song in songs if song.state in REVIEWABLE],
        queue=queue,
    )


def reviewable_draft(store: Store, song_id: int) -> tuple[Song, Proposal]:
    song = store.require(song_id, REVIEWABLE)
    if song.draft is None:
        raise CommandError(f"song {song_id} has no draft")
    return song, song.draft


def song_command(action: Callable[[Config, Store, int], Song]) -> Callable[[int], None]:
    def command(song_id: Annotated[int, typer.Argument(help="Song id")]) -> None:
        with session() as (cfg, store):
            emit(to_json(action(cfg, store, song_id)))

    command.__doc__ = action.__doc__
    return command


def _show(_cfg: Config, store: Store, song_id: int) -> Song:
    """Song detail with its proposals and the current draft."""
    return store.get(song_id)


app.command("show")(song_command(_show))


@app.command("list")
def list_songs(state: Annotated[State | None, typer.Option(help="Only songs in this state")] = None) -> None:
    """Songs, optionally filtered by state."""
    with session() as (_cfg, store):
        songs = store.songs((state,)) if state else store.all_songs()
        emit(to_json(SongList(songs=[SongSummary.of(song) for song in songs])))


@app.command()
def status() -> None:
    """Review count, work in flight and songs per state."""
    with session() as (cfg, store):
        emit(to_json(status_of(cfg, store)))


@app.command()
def watch(
    count: Annotated[int, typer.Option(help="Exit after this many events (0 = never)")] = 0,
) -> None:
    """Stream the status as one JSON line now and on every change."""
    with session() as (cfg, store):
        last = -1
        emitted = 0
        while count == 0 or emitted < count:
            if store.version() != last:
                current = status_of(cfg, store)
                last = current.version
                emit(to_json(current))
                emitted += 1
            else:
                time.sleep(WATCH_POLL)


@app.command()
def select(
    song_id: Annotated[int, typer.Argument(help="Song id")],
    index: Annotated[int, typer.Argument(help="Proposal index, as listed by `show`")],
) -> None:
    """Make a proposal the draft that will be confirmed."""
    with session() as (_cfg, store):
        emit(to_json(store.select(song_id, index)))


@app.command()
def edit(
    song_id: Annotated[int, typer.Argument(help="Song id")],
    assignments: Annotated[list[str], typer.Argument(help="FIELD=VALUE pairs; lists use ';'")],
) -> None:
    """Edit fields of the draft (title, artist, artists, album, album_artist, track, track_total,
    disc, disc_total, year, genre, compilation, mbid_recording, mbid_release, mbid_artist)."""
    with session() as (_cfg, store):
        _song, draft = reviewable_draft(store, song_id)
        emit(to_json(store.save_draft(song_id, review.apply_edits(draft, assignments))))


@app.command()
def cover(
    song_id: Annotated[int, typer.Argument(help="Song id")],
    thumbnail: Annotated[bool, typer.Option("--thumbnail", help="Use the YouTube thumbnail")] = False,
    url: Annotated[str | None, typer.Option(help="Download the cover from this http(s) URL")] = None,
    file: Annotated[Path | None, typer.Option(help="Use this local image")] = None,
) -> None:
    """Replace the draft's cover (always centre-cropped to a square)."""
    with session() as (_cfg, store):
        song, draft = reviewable_draft(store, song_id)
        if thumbnail:
            path = review.thumbnail_cover(song)
        elif url:
            path = review.cover_from_url(song, url)
        elif file:
            path = review.cover_from_file(song, file)
        else:
            raise CommandError("choose one of --thumbnail, --url or --file")
        emit(to_json(store.save_draft(song_id, replace(draft, cover=path))))


@app.command()
def preview(song_id: Annotated[int, typer.Argument(help="Song id")]) -> None:
    """Play the song's local audio."""
    with session() as (cfg, store):
        audio = review.preview(cfg, store.get(song_id))
        emit(to_json(PreviewOutput(id=song_id, audio=str(audio))))


def _confirm(_cfg: Config, store: Store, song_id: int) -> Song:
    """Send the song to Navidrome with the draft's metadata."""
    review.check_complete(store.require(song_id, (State.READY_FOR_REVIEW,)).draft)
    return store.confirm(song_id)


def _discard(cfg: Config, store: Store, song_id: int) -> Song:
    """Drop the song: delete its local audio and keep it in history as discarded."""
    return review.discard(cfg, store, song_id)


def _replace(_cfg: Config, store: Store, song_id: int) -> Song:
    """Send a conflicting song again, overwriting the file already in Navidrome."""
    return store.replace(song_id)


def _retry(_cfg: Config, store: Store, song_id: int) -> Song:
    """Send a failed song again."""
    return store.retry(song_id)


app.command("confirm")(song_command(_confirm))
app.command("discard")(song_command(_discard))
app.command("replace")(song_command(_replace))
app.command("retry")(song_command(_retry))


@app.command()
def history(
    q: Annotated[str | None, typer.Option("--q", help="Search title, artist, album and YouTube data")] = None,
    state: Annotated[State | None, typer.Option(help="Only songs in this final state")] = None,
) -> None:
    """Processed songs (sent, discarded, failed), newest first."""
    with session() as (_cfg, store):
        songs = store.history(q or "", state)
        emit(to_json(SongList(songs=[SongSummary.of(song) for song in songs])))


@app.command()
def daemon(once: Annotated[bool, typer.Option(help="Exit when there is no work left")] = False) -> None:
    """Run the background worker (processing and delivery)."""
    run_daemon(config.load(), once=once)


def main() -> None:
    app()
