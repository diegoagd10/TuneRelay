import hashlib
import shutil
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mutagen.mp4 import MP4, MP4Cover, MP4Tags

from conftest import FakeHttp, TuneRelay
from test_processing import codex_proposal

DEAD_END = Path("Cigar/Dead End (2019)/03 - Tombstone Boogie.m4a")


def confirmed(tr: TuneRelay, *edits: str) -> int:
    tr.codex_returns([codex_proposal()])
    song_id = tr.ready_for_review()
    if edits:
        tr.cli("edit", str(song_id), *edits)
    tr.cli("confirm", str(song_id))
    return song_id


def read_tags(path: Path) -> MP4Tags:
    tags = MP4(path).tags
    assert tags is not None
    return tags


def freeform(tags: MP4Tags, name: str) -> list[str]:
    return [bytes(value).decode() for value in tags[f"----:com.apple.iTunes:{name}"]]


def test_a_confirmed_song_lands_tagged_in_the_library(tr: TuneRelay) -> None:
    song_id = confirmed(tr, "artists=Cigar; Guest Singer")

    tr.daemon_once()

    delivered = tr.library / DEAD_END
    tags = read_tags(delivered)
    assert tags["©nam"] == ["Tombstone Boogie"]
    assert tags["©ART"] == ["Cigar"]
    assert freeform(tags, "ARTISTS") == ["Cigar", "Guest Singer"]
    assert tags["aART"] == ["Cigar"]
    assert tags["©alb"] == ["Dead End"]
    assert tags["trkn"] == [(3, 10)]
    assert tags["disk"] == [(1, 1)]
    assert tags["©day"] == ["2019"]
    assert tags["©gen"] == ["Rock"]
    assert tags["cpil"] is False
    assert freeform(tags, "MusicBrainz Track Id") == ["rec-1"]
    assert freeform(tags, "MusicBrainz Album Id") == ["rel-1"]
    assert freeform(tags, "MusicBrainz Artist Id") == ["art-1"]
    [art] = tags["covr"]
    assert art.imageformat == MP4Cover.FORMAT_JPEG
    assert (delivered.parent / "cover.jpg").read_bytes() == bytes(art)
    song = tr.song(song_id)
    assert song["state"] == "sent"
    assert song["remote_path"] == str(DEAD_END)
    assert tr.notifications()[-1] == "Sent to Navidrome | Cigar - Tombstone Boogie"


def test_the_local_audio_is_deleted_after_delivery_but_history_keeps_a_small_cover(tr: TuneRelay) -> None:
    song_id = confirmed(tr)

    tr.daemon_once()

    assert not (tr.inbox / "dQw4w9WgXcQ").exists()
    [entry] = tr.cli("history")["songs"]
    assert entry["id"] == song_id
    assert entry["remote_path"] == str(DEAD_END)
    assert Path(entry["cover"]).exists()


def test_a_single_goes_to_its_single_album_folder(tr: TuneRelay) -> None:
    song_id = tr.ready_for_review()
    tr.cli("confirm", str(song_id))

    tr.daemon_once()

    assert (tr.library / "Cigar/Tombstone Boogie (Single) (2024)/01 - Tombstone Boogie.m4a").exists()


def test_unsafe_characters_are_sanitised_in_the_destination(tr: TuneRelay) -> None:
    confirmed(tr, "album_artist=AC/DC", "album=..Live: At <Home>?", "title=What? / Why*", "year=")

    tr.daemon_once()

    assert (tr.library / "AC_DC/Live_ At _Home__/03 - What_ _ Why_.m4a").exists()


def test_a_transient_failure_is_retried_every_interval_until_it_heals(tr: TuneRelay) -> None:
    tr.configure("delivery", local_fail_times=2, retry_interval=0.3)
    song_id = confirmed(tr)

    started = time.monotonic()
    tr.daemon_once()

    assert time.monotonic() - started >= 0.6
    assert tr.song(song_id)["state"] == "sent"
    assert (tr.library / DEAD_END).exists()


def test_three_consecutive_failures_mark_the_song_failed_and_keep_the_local_audio(tr: TuneRelay) -> None:
    tr.configure("delivery", local_fail_times=3)
    song_id = confirmed(tr)

    tr.daemon_once()

    song = tr.song(song_id)
    assert song["state"] == "failed"
    assert song["attempts"] == 3
    assert song["error"] == "simulated transfer failure"
    assert (tr.inbox / "dQw4w9WgXcQ" / "audio.m4a").exists()
    assert tr.notifications()[-1] == "Delivery failed | Cigar - Tombstone Boogie\nsimulated transfer failure"
    assert [entry["state"] for entry in tr.cli("history", "--state", "failed")["songs"]] == ["failed"]


def test_a_failed_song_can_be_retried(tr: TuneRelay) -> None:
    tr.configure("delivery", local_fail_times=3)
    song_id = confirmed(tr)
    tr.daemon_once()
    tr.configure("delivery", local_fail_times=0)

    assert tr.cli("retry", str(song_id))["state"] == "in_transit"
    tr.daemon_once()

    assert tr.song(song_id)["state"] == "sent"
    assert tr.cli_error("retry", str(song_id)) == f"song {song_id} is sent; expected failed"


def test_an_existing_file_is_never_overwritten_and_the_song_returns_to_review(tr: TuneRelay) -> None:
    existing = tr.library / DEAD_END
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"the version already in Navidrome")
    song_id = confirmed(tr)

    tr.daemon_once()

    song = tr.song(song_id)
    assert song["state"] == "conflict"
    assert song["error"] == "already exists in Navidrome"
    assert existing.read_bytes() == b"the version already in Navidrome"
    assert [s["id"] for s in tr.cli("list", "--state", "conflict")["songs"]] == [song_id]


def test_replace_overwrites_the_existing_file(tr: TuneRelay) -> None:
    existing = tr.library / DEAD_END
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old")
    song_id = confirmed(tr)
    tr.daemon_once()

    assert tr.cli("replace", str(song_id))["state"] == "in_transit"
    tr.daemon_once()

    assert tr.song(song_id)["state"] == "sent"
    assert read_tags(existing)["©nam"] == ["Tombstone Boogie"]


def test_a_conflicting_song_can_be_discarded(tr: TuneRelay) -> None:
    existing = tr.library / DEAD_END
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old")
    song_id = confirmed(tr)
    tr.daemon_once()

    assert tr.cli("discard", str(song_id))["state"] == "discarded"
    assert existing.read_bytes() == b"old"


def test_a_scan_is_requested_from_navidrome_after_delivery(tr: TuneRelay, http: FakeHttp) -> None:
    tr.configure("scan", method="subsonic", url=http.url, user="dagd", password_entry="navidrome/dagd")
    tr.env["FAKE_PASS_OUTPUT"] = "hunter2"
    confirmed(tr)

    tr.daemon_once()

    [request] = http.requests
    url = urlparse(request)
    query = {key: values[0] for key, values in parse_qs(url.query).items()}
    assert url.path == "/rest/startScan.view"
    assert query["u"] == "dagd"
    assert query["t"] == hashlib.md5(("hunter2" + query["s"]).encode()).hexdigest()  # noqa: S324
    assert query["f"] == "json"
    assert tr.calls("pass")[0]["args"] == ["show", "navidrome/dagd"]


def test_no_scan_is_requested_when_delivery_fails(tr: TuneRelay, http: FakeHttp) -> None:
    tr.configure("scan", method="subsonic", url=http.url, user="dagd", password_entry="navidrome/dagd")
    tr.configure("delivery", local_fail_times=3)
    confirmed(tr)

    tr.daemon_once()

    assert http.requests == []


def test_a_failing_scan_is_reported_but_the_song_stays_sent(tr: TuneRelay, http: FakeHttp) -> None:
    tr.configure("scan", method="subsonic", url=http.url, user="dagd", password_entry="navidrome/dagd")
    http.status = 500
    song_id = confirmed(tr)

    tr.daemon_once()

    assert tr.song(song_id)["state"] == "sent"
    assert tr.notifications()[-1].startswith("Navidrome scan failed")


def use_ssh(tr: TuneRelay, music_dir: Path) -> None:
    tr.configure(
        "delivery",
        transport="ssh",
        hosts=["svc-02.lan", "svc-02.tailnet.ts.net"],
        user="dagd",
        music_dir=str(music_dir),
    )


def test_ssh_delivery_tries_the_lan_first_then_tailscale(tr: TuneRelay) -> None:
    music = tr.root / "svc-02 music"
    music.mkdir()
    use_ssh(tr, music)
    tr.env["FAKE_SSH_DOWN"] = "svc-02.lan"
    song_id = confirmed(tr)

    tr.daemon_once()

    assert tr.song(song_id)["state"] == "sent"
    assert read_tags(music / DEAD_END)["©alb"] == ["Dead End"]
    assert tr.calls("ssh")[0]["host"] == "svc-02.lan"
    assert {call["host"] for call in tr.calls("rsync")} == {"svc-02.tailnet.ts.net"}


def test_ssh_delivery_fails_when_no_host_is_reachable(tr: TuneRelay) -> None:
    use_ssh(tr, tr.root)
    tr.env["FAKE_SSH_DOWN"] = "svc-02.lan,svc-02.tailnet.ts.net"
    song_id = confirmed(tr)

    tr.daemon_once()

    song = tr.song(song_id)
    assert song["state"] == "failed"
    assert song["error"] == "svc-02 is unreachable (tried svc-02.lan, svc-02.tailnet.ts.net)"


def test_a_corrupted_copy_fails_verification_and_the_local_audio_is_kept(tr: TuneRelay) -> None:
    music = tr.root / "music"
    music.mkdir()
    use_ssh(tr, music)
    tr.env["FAKE_RSYNC_CORRUPT"] = "1"
    song_id = confirmed(tr)

    tr.daemon_once()

    song = tr.song(song_id)
    assert song["state"] == "failed"
    assert song["error"].startswith("verification failed")
    assert (tr.inbox / "dQw4w9WgXcQ" / "audio.m4a").exists()
    assert not (music / DEAD_END).exists()


def test_ssh_delivery_needs_the_server_settings(tr: TuneRelay) -> None:
    tr.configure("delivery", transport="ssh", hosts=[], music_dir="")
    song_id = confirmed(tr)

    tr.daemon_once()

    assert tr.song(song_id)["error"] == "config.toml is missing delivery.hosts, delivery.music_dir"


def test_a_song_left_in_transit_resumes_after_a_restart(tr: TuneRelay) -> None:
    song_id = confirmed(tr)
    shutil.rmtree(tr.library)
    tr.library.mkdir()

    tr.daemon_once()

    assert tr.song(song_id)["state"] == "sent"


def test_a_server_side_error_is_reported(tr: TuneRelay) -> None:
    blocker = tr.root / "not-a-folder"
    blocker.write_text("")
    use_ssh(tr, blocker)
    song_id = confirmed(tr)

    tr.daemon_once()

    song = tr.song(song_id)
    assert song["state"] == "failed"
    assert song["error"].startswith("mkdir failed on the server")


def test_a_byte_identical_file_already_on_the_server_counts_as_delivered(tr: TuneRelay) -> None:
    # Same metadata and audio as an earlier delivery, e.g. a crash after the copy but before it was recorded.
    first = confirmed(tr)
    tr.daemon_once()
    second = tr.ready_for_review("bbbbbbbbbbb")
    tr.cli("confirm", str(second))

    tr.daemon_once()

    assert tr.song(first)["state"] == "sent"
    assert tr.song(second)["state"] == "sent"


def test_after_editing_a_conflicting_song_it_can_be_confirmed_to_the_new_path(tr: TuneRelay) -> None:
    existing = tr.library / DEAD_END
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old")
    song_id = confirmed(tr)
    tr.daemon_once()

    tr.cli("edit", str(song_id), "title=Tombstone Boogie (Live)")
    assert tr.cli("confirm", str(song_id))["state"] == "in_transit"
    tr.daemon_once()

    assert tr.song(song_id)["state"] == "sent"
    assert existing.read_bytes() == b"old"
    assert (tr.library / "Cigar/Dead End (2019)/03 - Tombstone Boogie (Live).m4a").exists()


def test_replace_only_overwrites_the_file_that_conflicted(tr: TuneRelay) -> None:
    existing = tr.library / DEAD_END
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old")
    other = tr.library / "Cigar/Dead End (2019)/04 - Other Song.m4a"
    other.write_bytes(b"other")
    song_id = confirmed(tr)
    tr.daemon_once()

    tr.cli("edit", str(song_id), "title=Other Song", "track=4")
    tr.cli("replace", str(song_id))
    tr.daemon_once()

    assert tr.song(song_id)["state"] == "conflict"
    assert other.read_bytes() == b"other"
    assert existing.read_bytes() == b"old"


def test_a_corrupt_audio_file_fails_delivery_without_crashing_the_daemon(tr: TuneRelay) -> None:
    folder = tr.inbox / "broken"
    folder.mkdir(parents=True)
    (folder / "Broken - Song.m4a").write_bytes(b"this is not an mp4 file")
    (folder / "ready").touch()
    tr.daemon_once()
    [song] = tr.cli("list")["songs"]
    tr.cli("confirm", str(song["id"]))

    tr.daemon_once()

    assert tr.song(song["id"])["state"] == "failed"
    assert tr.song(song["id"])["error"].startswith("cannot tag the audio")
