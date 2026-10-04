"""`tunerelay-host`: the native messaging host the browser extension talks to.

The browser starts it with one frame (`{"url": ...}`) on stdin. It answers
quickly and detaches a worker (`--download SONG_ID`) that runs yt-dlp, so the
browser's port is freed while the download continues.
"""

import json
import os
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO

from tunerelay import config, inbox, notify, youtube
from tunerelay.jsondata import JsonObject
from tunerelay.store import CaptureResult, Song, State, Store, StoreError, YouTubeInfo

MAX_FRAME = 1024 * 1024
DUPLICATE_STATES = {
    State.DOWNLOADING: "is already downloading",
    State.QUEUED: "is already queued",
    State.PROCESSING: "is already being processed",
    State.READY_FOR_REVIEW: "is already waiting for review",
    State.CONFLICT: "is already waiting for review",
    State.IN_TRANSIT: "is already in transit",
    State.SENT: "was already sent to Navidrome",
    State.FAILED: "already failed to send; retry it from TuneRelay",
}


@dataclass(frozen=True)
class SongRef:
    id: int
    video_id: str
    state: str


@dataclass(frozen=True)
class Reply:
    status: str  # "accepted", "duplicate" or "error"
    message: str
    song: SongRef | None = None


def read_frame(stream: BinaryIO) -> JsonObject | None:
    header = stream.read(4)
    if len(header) != 4:
        return None
    (length,) = struct.unpack("<I", header)
    if not 0 < length <= MAX_FRAME:
        return None
    try:
        return JsonObject.parse(stream.read(length).decode())
    except (ValueError, UnicodeDecodeError):
        return None


def write_frame(stream: BinaryIO, reply: Reply) -> None:
    payload = json.dumps(asdict(reply), ensure_ascii=False).encode()
    stream.write(struct.pack("<I", len(payload)) + payload)
    stream.flush()


def _ref(song: Song) -> SongRef:
    return SongRef(id=song.id, video_id=song.video_id, state=song.state)


def _song_name(song: Song) -> str:
    return song.youtube.title if song.youtube and song.youtube.title else song.url


def capture(cfg: config.Config, url: str) -> Reply:
    try:
        video_id = youtube.normalize_url(url)
    except youtube.InvalidUrlError:
        notify.send(cfg, "Download failed", f"Not a YouTube video: {url}", critical=True)
        return Reply(status="error", message="not a YouTube video URL")
    store = Store(cfg.database)
    try:
        folder = cfg.inbox / video_id
        result: CaptureResult = store.claim_capture(
            video_id, youtube.canonical_url(video_id), folder, owner_pid=os.getpid()
        )
    finally:
        store.close()
    if not result.accepted:
        message = f"{_song_name(result.song)} {DUPLICATE_STATES[result.song.state]}"
        notify.send(cfg, "Already in TuneRelay", message)
        return Reply(status="duplicate", message=message, song=_ref(result.song))
    shutil.rmtree(folder, ignore_errors=True)
    worker = subprocess.Popen(
        [sys.executable, "-m", "tunerelay.host", "--download", str(result.song.id)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    store = Store(cfg.database)
    try:
        store.set_worker(result.song.id, worker.pid)
    finally:
        store.close()
    return Reply(status="accepted", message="download started", song=_ref(result.song))


def run_download(cfg: config.Config, song_id: int) -> None:
    """The detached worker: download, then mark the folder ready and queue the song."""
    store = Store(cfg.database)
    try:
        song = store.get(song_id)
        folder = Path(song.folder)
        last_update = 0.0

        def on_progress(percent: int) -> None:
            nonlocal last_update
            now = time.monotonic()
            if percent < 100 and now - last_update < 0.25:
                return
            last_update = now
            notify.osd_progress(cfg, percent)
            store.set_progress(song_id, percent)

        error = youtube.download(cfg, song.video_id, folder, on_progress)
        info: YouTubeInfo | None = None
        if error is None:
            try:
                info = inbox.read_info(folder, song.video_id)
                inbox.mark_ready(folder)
            except OSError as failure:
                error = f"cannot finish the download in {folder}: {failure.strerror or failure}"
        if error is not None or info is None:
            error = error or "the download did not finish"
            if folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)
            store.mark_download_failed(song_id, error)
            notify.send(cfg, "Download failed", f"{song.url}\n{error}", critical=True)
            return
        store.mark_downloaded(song_id, info)
        notify.send(cfg, "Queued", info.title or song.url)
    except StoreError:
        return  # the song changed under us (e.g. adopted by the daemon); nothing left to do
    finally:
        store.close()


def with_desktop_path(path: str) -> str:
    """The browser starts the host without the session PATH; add where yt-dlp and omarchy-osd live."""
    omarchy = os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")
    wanted = [str(Path.home() / ".local/bin"), f"{omarchy}/bin", "/usr/local/bin", "/usr/bin"]
    present = path.split(os.pathsep) if path else []
    return os.pathsep.join(present + [entry for entry in wanted if entry not in present])


def main() -> None:
    os.environ["PATH"] = with_desktop_path(os.environ.get("PATH", ""))
    cfg = config.load()
    if len(sys.argv) >= 3 and sys.argv[1] == "--download":
        run_download(cfg, int(sys.argv[2]))
        return
    message = read_frame(sys.stdin.buffer)
    url = message.text("url") if message else None
    reply = capture(cfg, url) if url else Reply(status="error", message='expected {"url": ...}')
    write_frame(sys.stdout.buffer, reply)


if __name__ == "__main__":
    main()
