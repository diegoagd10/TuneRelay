from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import TuneRelay


def test_capture_downloads_m4a_info_and_thumbnail_into_the_inbox(tr: TuneRelay) -> None:
    song_id = tr.capture("dQw4w9WgXcQ")

    folder = tr.inbox / "dQw4w9WgXcQ"
    assert sorted(p.name for p in folder.iterdir()) == ["audio.info.json", "audio.jpg", "audio.m4a", "ready"]
    song = tr.song(song_id)
    assert song["video_id"] == "dQw4w9WgXcQ"
    assert song["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert song["youtube"]["title"] == "Cigar - Tombstone Boogie"
    assert song["youtube"]["channel"] == "Cigar - Topic"
    args = tr.calls("yt-dlp")[0]["args"]
    assert "--no-playlist" in args
    assert args[args.index("-f") + 1] == "bestaudio[ext=m4a]"
    assert "-x" not in args and "--audio-format" not in args


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890&index=3",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=RDAMVM",
        "https://youtu.be/dQw4w9WgXcQ?si=abc&list=PL1",
        "https://m.youtube.com/shorts/dQw4w9WgXcQ",
    ],
)
def test_only_the_current_video_is_captured_whatever_the_url_shape(tr: TuneRelay, url: str) -> None:
    reply = tr.host({"url": url})

    assert reply["status"] == "accepted"
    assert reply["song"]["video_id"] == "dQw4w9WgXcQ"
    song = tr.wait_for_state(reply["song"]["id"], "queued")
    assert song["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert tr.calls("yt-dlp")[0]["args"][-1] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    ["https://example.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/playlist?list=PL1", "not a url"],
)
def test_a_url_that_is_not_a_youtube_video_is_rejected_with_a_notification(tr: TuneRelay, url: str) -> None:
    reply = tr.host({"url": url})

    assert reply["status"] == "error"
    assert tr.notifications() == [f"Download failed | Not a YouTube video: {url}"]
    assert tr.calls("yt-dlp") == []


def test_a_malformed_message_gets_an_error_reply(tr: TuneRelay) -> None:
    assert tr.host({"href": "https://youtu.be/dQw4w9WgXcQ"})["status"] == "error"


def test_download_progress_goes_to_the_osd_and_completion_to_a_queued_notification(tr: TuneRelay) -> None:
    tr.capture()

    percents = [call["args"][call["args"].index("-p") + 1] for call in tr.calls("omarchy-osd")]
    assert percents[0] == "0"
    assert percents[-1] == "100"
    assert tr.notifications() == ["Queued | Cigar - Tombstone Boogie"]


def test_capturing_a_known_video_is_reported_as_a_duplicate(tr: TuneRelay) -> None:
    song_id = tr.capture()

    reply = tr.host({"url": "https://music.youtube.com/watch?v=dQw4w9WgXcQ"})

    assert reply["status"] == "duplicate"
    assert reply["song"] == {"id": song_id, "video_id": "dQw4w9WgXcQ", "state": "queued"}
    assert tr.notifications()[-1] == "Already in TuneRelay | Cigar - Tombstone Boogie is already queued"
    assert len(tr.calls("yt-dlp")) == 1


def test_a_failed_download_is_notified_and_leaves_nothing_in_the_inbox(tr: TuneRelay) -> None:
    tr.env["FAKE_YTDLP_MODE"] = "fail"

    reply = tr.host({"url": "https://youtu.be/dQw4w9WgXcQ"})

    song = tr.wait_for_state(reply["song"]["id"], "download_failed")
    assert song["error"] == "ERROR: [youtube] Video unavailable"
    assert not (tr.inbox / "dQw4w9WgXcQ").exists()
    assert tr.notifications() == [
        "Download failed | https://www.youtube.com/watch?v=dQw4w9WgXcQ\nERROR: [youtube] Video unavailable"
    ]


def test_a_video_whose_download_failed_can_be_captured_again(tr: TuneRelay) -> None:
    tr.env["FAKE_YTDLP_MODE"] = "fail"
    first = tr.host({"url": "https://youtu.be/dQw4w9WgXcQ"})
    tr.wait_for_state(first["song"]["id"], "download_failed")
    del tr.env["FAKE_YTDLP_MODE"]

    assert tr.capture() == first["song"]["id"]


@pytest.mark.parametrize(
    "frame",
    [b"", b"\x05\x00\x00\x00{bad}", b"\x02\x00\x00\x00[]", b"\x00\x00\x00\x00", b"\xff\xff\xff\xff"],
    ids=["empty", "bad-json", "not-an-object", "zero-length", "too-long"],
)
def test_a_broken_native_messaging_frame_gets_an_error_reply(tr: TuneRelay, frame: bytes) -> None:
    assert tr.host_raw(frame)["status"] == "error"


def test_a_download_without_m4a_audio_fails(tr: TuneRelay) -> None:
    tr.env["FAKE_YTDLP_MODE"] = "noaudio"

    reply = tr.host({"url": "https://youtu.be/dQw4w9WgXcQ"})

    assert (
        tr.wait_for_state(reply["song"]["id"], "download_failed")["error"]
        == "yt-dlp did not produce an M4A file"
    )


def test_simultaneous_captures_of_one_video_accept_only_one(tr: TuneRelay) -> None:
    tr.env["FAKE_YTDLP_DELAY"] = "1"
    for video_id in ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"):
        url = f"https://youtu.be/{video_id}"
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(tr.host, [{"url": url}, {"url": url}]))
        assert sorted(reply["status"] for reply in replies) == ["accepted", "duplicate"]


def test_a_missing_downloader_is_a_notified_download_failure(tr: TuneRelay) -> None:
    tr.configure("tools", ytdlp=str(tr.root / "no-such-yt-dlp"))

    reply = tr.host({"url": "https://youtu.be/dQw4w9WgXcQ"})

    song = tr.wait_for_state(reply["song"]["id"], "download_failed")
    assert song["error"].startswith("cannot run yt-dlp")
    assert tr.notifications()[-1].startswith("Download failed | https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_an_inbox_that_cannot_be_created_is_a_notified_download_failure(tr: TuneRelay) -> None:
    tr.inbox.write_text("not a folder")

    reply = tr.host({"url": "https://youtu.be/dQw4w9WgXcQ"})

    song = tr.wait_for_state(reply["song"]["id"], "download_failed")
    assert song["error"].startswith("cannot create the download folder")
    assert tr.notifications()[-1].startswith("Download failed | https://www.youtube.com/watch?v=dQw4w9WgXcQ")
