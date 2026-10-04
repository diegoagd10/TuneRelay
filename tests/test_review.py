import shutil
import subprocess
from pathlib import Path

from PIL import Image

from conftest import FAKES, FakeHttp, TuneRelay, rgb, wait_until
from test_processing import codex_proposal


def review_with_codex(tr: TuneRelay) -> int:
    tr.codex_returns([codex_proposal(album="Dead End", confidence=0.86)])
    return tr.ready_for_review()


def test_selecting_another_proposal_makes_it_the_draft(tr: TuneRelay) -> None:
    song_id = review_with_codex(tr)

    song = tr.cli("select", str(song_id), "1")

    assert song["selected"] == 1
    assert song["draft"]["album"] == "Tombstone Boogie (Single)"
    assert tr.song(song_id)["draft"]["origin"] == "youtube-default"


def test_selecting_a_missing_proposal_is_an_error(tr: TuneRelay) -> None:
    song_id = review_with_codex(tr)

    assert tr.cli_error("select", str(song_id), "5") == f"song {song_id} has no proposal 5"


def test_every_field_of_the_draft_can_be_edited(tr: TuneRelay) -> None:
    song_id = review_with_codex(tr)

    song = tr.cli(
        "edit",
        str(song_id),
        "title=Tombstone Boogie (Remastered)",
        "artist=CIGAR",
        "artists=CIGAR; Guest Singer",
        "album=Dead End Deluxe",
        "album_artist=Various Artists",
        "track=4",
        "track_total=12",
        "disc=2",
        "disc_total=2",
        "year=2020",
        "genre=Blues Rock",
        "compilation=true",
        "mbid_recording=rec-9",
    )

    draft = song["draft"]
    assert draft["title"] == "Tombstone Boogie (Remastered)"
    assert draft["artist"] == "CIGAR"
    assert draft["artists"] == ["CIGAR", "Guest Singer"]
    assert draft["album"] == "Dead End Deluxe"
    assert draft["album_artist"] == "Various Artists"
    assert (draft["track"], draft["track_total"], draft["disc"], draft["disc_total"]) == (4, 12, 2, 2)
    assert draft["year"] == 2020
    assert draft["genre"] == "Blues Rock"
    assert draft["compilation"] is True
    assert draft["mbids"] == {"recording": "rec-9", "release": "rel-1", "artist": "art-1"}
    assert tr.song(song_id)["draft"] == draft


def test_editing_the_artist_keeps_a_single_artist_list_in_step(tr: TuneRelay) -> None:
    song_id = review_with_codex(tr)

    draft = tr.cli("edit", str(song_id), "artist=CIGAR")["draft"]

    assert draft["artists"] == ["CIGAR"]


def test_clearing_optional_fields(tr: TuneRelay) -> None:
    song_id = review_with_codex(tr)

    draft = tr.cli("edit", str(song_id), "year=", "genre=", "mbid_release=")["draft"]

    assert draft["year"] is None
    assert draft["genre"] is None
    assert "release" not in draft["mbids"]


def test_invalid_edits_are_rejected(tr: TuneRelay) -> None:
    song_id = review_with_codex(tr)

    assert tr.cli_error("edit", str(song_id), "colour=red") == "unknown field: colour"
    assert tr.cli_error("edit", str(song_id), "track=three") == "track must be a whole number"
    assert tr.cli_error("edit", str(song_id), "title") == "expected FIELD=VALUE, got: title"
    assert tr.cli_error("edit", str(song_id), "title=") == "title cannot be empty"
    assert tr.cli_error("edit", str(song_id), "compilation=maybe") == "compilation must be true or false"


def test_the_cover_can_be_replaced_by_a_local_file_a_url_or_the_thumbnail(
    tr: TuneRelay, http: FakeHttp
) -> None:
    song_id = review_with_codex(tr)
    thumbnail_cover = tr.song(song_id)["draft"]["cover"]

    from_file = tr.cli("cover", str(song_id), "--file", str(FAKES / "cover.png"))["draft"]["cover"]
    red, green, blue = rgb(from_file, 10, 10)
    assert green > 150 and red < 100

    http.files["/art.jpg"] = (FAKES / "thumb.jpg").read_bytes()
    from_url = tr.cli("cover", str(song_id), "--url", f"{http.url}/art.jpg")["draft"]["cover"]
    assert Image.open(from_url).size == (180, 180)
    assert from_url != from_file

    assert tr.cli("cover", str(song_id), "--thumbnail")["draft"]["cover"] == thumbnail_cover


def test_unusable_covers_are_rejected(tr: TuneRelay, tmp_path: Path) -> None:
    song_id = review_with_codex(tr)
    text_file = tmp_path / "notes.txt"
    text_file.write_text("not an image")

    assert tr.cli_error("cover", str(song_id), "--file", str(text_file)).startswith("not a usable image")
    assert tr.cli_error("cover", str(song_id), "--url", "file:///etc/passwd").startswith(
        "cover URL must be http"
    )
    assert tr.cli_error("cover", str(song_id)) == "choose one of --thumbnail, --url or --file"


def test_preview_plays_the_local_audio(tr: TuneRelay) -> None:
    song_id = tr.ready_for_review()

    result = tr.cli("preview", str(song_id))

    audio = str(tr.inbox / "dQw4w9WgXcQ" / "audio.m4a")
    assert result["audio"] == audio
    wait_until(lambda: len(tr.calls("mpv")) == 1)
    assert tr.calls("mpv")[0]["args"][-1] == audio


def test_discard_deletes_the_local_audio_and_keeps_the_song_in_history(tr: TuneRelay) -> None:
    song_id = tr.ready_for_review()

    song = tr.cli("discard", str(song_id))

    assert song["state"] == "discarded"
    assert not (tr.inbox / "dQw4w9WgXcQ").exists()
    assert Path(song["history_cover"]).exists()
    assert Image.open(song["history_cover"]).size == (180, 180)
    [entry] = tr.cli("history")["songs"]
    assert (entry["id"], entry["state"]) == (song_id, "discarded")


def test_a_discarded_video_can_be_captured_again(tr: TuneRelay) -> None:
    song_id = tr.ready_for_review()
    tr.cli("discard", str(song_id))

    reply = tr.host({"url": "https://youtu.be/dQw4w9WgXcQ"})

    assert reply["status"] == "accepted"
    tr.wait_for_state(song_id, "queued")
    tr.daemon_once()
    assert tr.song(song_id)["state"] == "ready_for_review"


def test_confirm_sends_the_song_on_its_way(tr: TuneRelay) -> None:
    song_id = tr.ready_for_review()

    assert tr.cli("confirm", str(song_id))["state"] == "in_transit"
    assert (
        tr.cli_error("confirm", str(song_id))
        == f"song {song_id} is in_transit; expected ready_for_review, conflict"
    )


def test_review_actions_need_a_song_in_review(tr: TuneRelay) -> None:
    song_id = tr.capture()

    assert tr.cli_error("select", str(song_id), "0").startswith(f"song {song_id} is queued")
    assert tr.cli_error("edit", str(song_id), "title=x").startswith(f"song {song_id} is queued")
    assert tr.cli_error("discard", str(song_id)).startswith(f"song {song_id} is queued")
    assert tr.cli_error("show", "999") == "no song with id 999"


def test_a_proposal_missing_required_fields_cannot_be_confirmed(tr: TuneRelay) -> None:
    tr.codex_returns([codex_proposal(album="")])
    song_id = tr.ready_for_review()

    assert tr.cli_error("confirm", str(song_id)) == "album cannot be empty"
    assert tr.song(song_id)["state"] == "ready_for_review"


def test_a_manual_drop_has_no_thumbnail_to_fall_back_to(tr: TuneRelay) -> None:
    folder = tr.inbox / "rain"
    folder.mkdir(parents=True)
    shutil.copy(FAKES / "tiny.m4a", folder / "Rain.m4a")
    (folder / "ready").touch()
    tr.daemon_once()
    [song] = tr.cli("list")["songs"]

    assert tr.cli_error("cover", str(song["id"]), "--thumbnail") == "this song has no thumbnail"
    assert tr.cli("discard", str(song["id"]))["history_cover"] is None
    assert tr.cli_error("preview", str(song["id"])) == f"song {song['id']} has no local audio"


def test_preview_stops_the_previous_preview_player(tr: TuneRelay) -> None:
    tr.configure("tools", player=str(FAKES / "slow-player"))
    song_id = tr.ready_for_review()
    tr.cli("preview", str(song_id))
    wait_until(lambda: len(tr.calls("slow-player")) == 1)
    first = tr.calls("slow-player")[0]["pid"]

    tr.cli("preview", str(song_id))

    wait_until(
        lambda: (
            not Path(f"/proc/{first}").exists() or "Z" in Path(f"/proc/{first}/stat").read_text().split()[2]
        )
    )


def test_preview_never_signals_a_process_it_did_not_start(tr: TuneRelay) -> None:
    song_id = tr.ready_for_review()
    unrelated = subprocess.Popen(["sleep", "60"])
    (tr.home / "preview.pid").write_text(str(unrelated.pid))

    tr.cli("preview", str(song_id))

    assert unrelated.poll() is None
    unrelated.kill()
    unrelated.wait()


def test_a_missing_preview_player_is_a_json_error(tr: TuneRelay) -> None:
    tr.configure("tools", player=str(tr.root / "no-such-player"))
    song_id = tr.ready_for_review()

    assert tr.cli_error("preview", str(song_id)).startswith("cannot start the preview player")
