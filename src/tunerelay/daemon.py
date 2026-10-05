"""The background worker: adopts ready inbox folders, processes and delivers one song at a time."""

import fcntl
import shutil
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from mutagen import MutagenError

from tunerelay import covers, delivery, inbox, notify, proposals, resolver, review, scanner, tagger
from tunerelay.config import Config, ConfigError
from tunerelay.delivery import DeliveryError, DeliveryOutcome
from tunerelay.store import RECAPTURABLE, Proposal, Song, State, Store

IDLE_POLL = 1.0


def describe(proposal: Proposal | None) -> str:
    return f"{proposal.artist} - {proposal.title}" if proposal else ""


def adopt_ready_folders(cfg: Config, store: Store) -> None:
    """Queue inbox folders carrying the `ready` marker that TuneRelay does not know yet (manual drops)."""
    if not cfg.inbox.exists():
        return
    for folder in sorted(cfg.inbox.iterdir()):
        if not folder.is_dir() or not inbox.is_ready(folder):
            continue
        audio = inbox.audio_file(folder)
        if audio is None:
            continue
        known = store.find_video(folder.name)
        if known is not None and known.state not in RECAPTURABLE:
            continue
        store.adopt(folder.name, "", folder, inbox.read_info(folder, audio.stem))


def process(cfg: Config, store: Store, song: Song) -> None:
    folder = Path(song.folder)
    info = song.youtube or inbox.read_info(folder, song.video_id)
    thumbnail = inbox.thumbnail_file(folder)
    cover: str | None = None
    if thumbnail is not None:
        try:
            cover = str(covers.square_file(thumbnail, folder / "cover.jpg"))
        except covers.CoverError:
            cover = None
    default = proposals.default_proposal(info, song.url, cover)
    found = resolver.resolve(cfg, info, folder, cover)
    song = store.finish_processing(song.id, [*found, default])
    notify.send(cfg, "Ready for review", describe(song.draft))


def attempt_delivery(song: Song, transport: delivery.Transport) -> delivery.DeliveryResult:
    """Tag and send the song once. Raises DeliveryError when the attempt fails."""
    audio = inbox.audio_file(Path(song.folder))
    if audio is None or song.draft is None:
        raise DeliveryError("the local audio is missing")
    try:
        tagger.write(audio, song.draft)
    except MutagenError as error:
        raise DeliveryError(f"cannot tag the audio: {error}") from error
    replace = PurePosixPath(song.remote_path) if song.overwrite and song.remote_path else None
    return delivery.deliver(audio, song.draft, transport, replace=replace)


def deliver(cfg: Config, store: Store, song: Song) -> None:
    """Send an in-transit song, retrying every `retry_interval` until it is sent, conflicts or fails."""
    name = describe(song.draft)
    transport: delivery.Transport | None = None
    while True:
        try:
            transport = transport or delivery.transport_for(cfg)
            result = attempt_delivery(song, transport)
        except (DeliveryError, ConfigError, OSError) as error:
            song = store.record_failure(song.id, str(error), cfg.delivery.max_attempts)
            if song.state == State.FAILED:
                notify.send(cfg, "Delivery failed", f"{name}\n{error}", critical=True)
                return
            time.sleep(cfg.delivery.retry_interval)
            continue
        break
    if result.outcome == DeliveryOutcome.CONFLICT:
        store.mark_conflict(song.id, str(result.remote_path))
        notify.send(cfg, "Already exists in Navidrome", f"{name}\n{result.remote_path}", critical=True)
        return
    store.mark_sent(song.id, str(result.remote_path), review.history_cover(cfg, song))
    shutil.rmtree(song.folder, ignore_errors=True)
    notify.send(cfg, "Sent to Navidrome", name)
    try:
        scanner.trigger_scan(cfg)
    except (scanner.ScanError, ConfigError) as error:
        notify.send(cfg, "Navidrome scan failed", str(error))


def step(cfg: Config, store: Store) -> bool:
    """Do one unit of work. Returns False when there is nothing to do."""
    adopt_ready_folders(cfg, store)
    song = store.start_processing()
    if song is not None:
        process(cfg, store, song)
        return True
    song = store.next_in_transit()
    if song is not None:
        deliver(cfg, store, song)
        return True
    return False


class DaemonBusyError(Exception):
    """Another daemon already owns the worker (processing is strictly one song at a time)."""


@contextmanager
def exclusive(cfg: Config) -> Generator[None]:
    """Hold the daemon lock for the worker's lifetime; the kernel drops it if the process dies."""
    with (cfg.home / "daemon.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise DaemonBusyError("another TuneRelay daemon is running") from error
        yield


def run(cfg: Config, *, once: bool) -> None:
    with exclusive(cfg):
        _work(cfg, once=once)


def _work(cfg: Config, *, once: bool) -> None:
    store = Store(cfg.database)
    try:
        store.recover()
        while True:
            if not step(cfg, store):
                if once:
                    return
                time.sleep(IDLE_POLL)
    finally:
        store.close()
