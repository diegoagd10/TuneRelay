import shutil
import signal
import subprocess

from conftest import BIN, FAKES, TuneRelay, wait_until


def drop_folder(tr: TuneRelay, name: str, *, ready: bool) -> None:
    folder = tr.inbox / name
    folder.mkdir(parents=True)
    shutil.copy(FAKES / "tiny.m4a", folder / "Liv Lingive - Rain.m4a")
    if ready:
        (folder / "ready").touch()


def test_a_folder_without_the_ready_marker_is_never_processed(tr: TuneRelay) -> None:
    drop_folder(tr, "rain", ready=False)

    tr.daemon_once()

    assert tr.cli("list")["songs"] == []


def test_a_manually_dropped_ready_folder_is_processed(tr: TuneRelay) -> None:
    drop_folder(tr, "rain", ready=True)

    tr.daemon_once()

    [song] = tr.cli("list", "--state", "ready_for_review")["songs"]
    assert song["video_id"] == "rain"
    default = tr.song(song["id"])["proposals"][-1]
    assert (default["artist"], default["title"]) == ("Liv Lingive", "Rain")
    assert default["cover"] is None


def test_an_in_progress_download_is_not_picked_up(tr: TuneRelay) -> None:
    tr.env["FAKE_YTDLP_DELAY"] = "3"
    reply = tr.host({"url": "https://youtu.be/dQw4w9WgXcQ"})
    wait_until((tr.inbox / "dQw4w9WgXcQ" / "audio.m4a.part").exists)

    tr.daemon_once()

    assert tr.song(reply["song"]["id"])["state"] == "downloading"
    tr.wait_for_state(reply["song"]["id"], "queued")


def test_a_song_interrupted_mid_processing_is_requeued_on_restart(tr: TuneRelay) -> None:
    song_id = tr.capture()
    tr.env["FAKE_CODEX_MODE"] = "hang"
    tr.configure("codex", timeout=60)
    daemon = subprocess.Popen([str(BIN / "tunerelay"), "daemon"], env=tr.env)
    tr.wait_for_state(song_id, "processing")
    daemon.send_signal(signal.SIGKILL)
    daemon.wait()

    del tr.env["FAKE_CODEX_MODE"]
    tr.daemon_once()

    assert tr.song(song_id)["state"] == "ready_for_review"
