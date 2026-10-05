import json

from PIL import Image

from conftest import FAKES, FakeHttp, TuneRelay, rgb


def youtube_info(tr: TuneRelay, **info: str | int) -> None:
    path = tr.root / "info.json"
    path.write_text(json.dumps(info))
    tr.env["FAKE_YTDLP_INFO"] = str(path)


def test_processing_builds_a_default_proposal_from_the_youtube_data(tr: TuneRelay) -> None:
    song_id = tr.ready_for_review()

    song = tr.song(song_id)
    [default] = song["proposals"]
    assert default["origin"] == "youtube-default"
    assert default["title"] == "Tombstone Boogie"
    assert default["artist"] == "Cigar"
    assert default["artists"] == ["Cigar"]
    assert default["album"] == "Tombstone Boogie (Single)"
    assert default["album_artist"] == "Cigar"
    assert (default["track"], default["track_total"], default["disc"], default["disc_total"]) == (1, 1, 1, 1)
    assert default["year"] == 2024
    assert default["compilation"] is False
    assert default["sources"] == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    assert song["selected"] == 0
    assert song["draft"] == default
    assert tr.notifications()[-1] == "Ready for review | Cigar - Tombstone Boogie"


def test_the_default_cover_is_the_thumbnail_centre_cropped_to_a_square(tr: TuneRelay) -> None:
    song_id = tr.ready_for_review()

    cover = tr.song(song_id)["draft"]["cover"]
    assert Image.open(cover).size == (180, 180)
    # The fake thumbnail is red on both sides and blue in the centre square.
    red, green, blue = rgb(cover, 2, 90)
    assert blue > 150 and red < 100
    red, green, blue = rgb(cover, 177, 90)
    assert blue > 150 and red < 100


def test_channel_suffixes_are_stripped_and_a_plain_title_is_kept_whole(tr: TuneRelay) -> None:
    youtube_info(tr, channel="CigarVEVO", title="Tombstone Boogie (Official Video)", upload_date="20190301")

    song = tr.song(tr.ready_for_review())

    default = song["proposals"][0]
    assert default["artist"] == "Cigar"
    assert default["title"] == "Tombstone Boogie (Official Video)"
    assert default["album"] == "Tombstone Boogie (Official Video) (Single)"
    assert default["year"] == 2019


def test_artist_dash_title_is_parsed_with_any_dash_style(tr: TuneRelay) -> None:
    youtube_info(tr, channel="Liv Lingive - Topic", title="Liv Lingive — Rain")

    default = tr.song(tr.ready_for_review())["proposals"][0]

    assert (default["artist"], default["title"]) == ("Liv Lingive", "Rain")


def codex_proposal(**fields: str | int | float | list[str] | dict[str, str] | None) -> dict:
    proposal = {
        "title": "Tombstone Boogie",
        "artist": "Cigar",
        "artists": ["Cigar"],
        "album": "Dead End",
        "album_artist": "Cigar",
        "track": 3,
        "track_total": 10,
        "disc": 1,
        "disc_total": 1,
        "year": 2019,
        "genre": "Rock",
        "compilation": False,
        "mbids": {"recording": "rec-1", "release": "rel-1", "artist": "art-1"},
        "confidence": 0.86,
        "sources": ["https://cigar.bandcamp.com/album/dead-end"],
        "cover_url": None,
    }
    proposal.update(fields)
    return proposal


def test_codex_proposals_are_ranked_by_confidence_before_the_default(tr: TuneRelay) -> None:
    tr.codex_returns(
        [
            codex_proposal(album="Live 2021", confidence=0.61),
            codex_proposal(album="Dead End", confidence=0.86),
        ]
    )

    song = tr.song(tr.ready_for_review())

    assert [(p["origin"], p["album"]) for p in song["proposals"]] == [
        ("codex", "Dead End"),
        ("codex", "Live 2021"),
        ("youtube-default", "Tombstone Boogie (Single)"),
    ]
    assert song["selected"] == 0
    assert song["draft"]["album"] == "Dead End"
    assert song["draft"]["mbids"] == {"recording": "rec-1", "release": "rel-1", "artist": "art-1"}
    assert song["draft"]["genre"] == "Rock"


def test_sourceless_and_low_confidence_proposals_are_dropped_and_at_most_three_kept(tr: TuneRelay) -> None:
    tr.codex_returns(
        [
            codex_proposal(album="No sources", sources=[]),
            codex_proposal(album="Unsure", confidence=0.49),
            codex_proposal(album="A", confidence=0.9),
            codex_proposal(album="B", confidence=0.8),
            codex_proposal(album="C", confidence=0.7),
            codex_proposal(album="D", confidence=0.6),
        ]
    )

    song = tr.song(tr.ready_for_review())

    assert [p["album"] for p in song["proposals"]] == ["A", "B", "C", "Tombstone Boogie (Single)"]


def test_codex_gets_the_youtube_context_and_runs_with_web_search_and_medium_effort(tr: TuneRelay) -> None:
    youtube_info(
        tr,
        description="Taken from the album Dead End",
        duration=221,
        chapters=[{"title": "Intro"}, {"title": "Tombstone Boogie"}],  # type: ignore[list-item]
    )

    tr.ready_for_review()

    [call] = tr.calls("codex")
    assert "--search" in call["args"]
    assert 'model_reasoning_effort="medium"' in call["args"]
    for expected in (
        "Cigar - Tombstone Boogie",
        "Cigar - Topic",
        "Taken from the album Dead End",
        "3:41",
        "Intro",
    ):
        assert expected in call["prompt"]


def test_a_failing_codex_is_retried_once_then_the_default_proposal_is_used(tr: TuneRelay) -> None:
    tr.env["FAKE_CODEX_MODE"] = "fail"

    song = tr.song(tr.ready_for_review())

    assert len(tr.calls("codex")) == 2
    assert [p["origin"] for p in song["proposals"]] == ["youtube-default"]


def test_a_hanging_codex_times_out(tr: TuneRelay) -> None:
    tr.env["FAKE_CODEX_MODE"] = "hang"
    tr.configure("codex", timeout=0.5)

    song = tr.song(tr.ready_for_review())

    assert len(tr.calls("codex")) == 2
    assert [p["origin"] for p in song["proposals"]] == ["youtube-default"]


def test_malformed_codex_output_falls_back_to_the_default(tr: TuneRelay) -> None:
    path = tr.root / "codex-output.json"
    path.write_text("Sure! Here is the metadata: ...")
    tr.env["FAKE_CODEX_OUTPUT"] = str(path)

    song = tr.song(tr.ready_for_review())

    assert [p["origin"] for p in song["proposals"]] == ["youtube-default"]


def test_a_codex_cover_url_is_downloaded_and_squared(tr: TuneRelay, http: FakeHttp) -> None:
    http.files["/dead-end.png"] = (FAKES / "cover.png").read_bytes()
    tr.codex_returns(
        [
            codex_proposal(cover_url=f"{http.url}/dead-end.png", confidence=0.9),
            codex_proposal(album="Broken cover", cover_url=f"{http.url}/missing.png", confidence=0.8),
        ]
    )

    song = tr.song(tr.ready_for_review())

    with_cover, broken, default = song["proposals"]
    red, green, blue = rgb(with_cover["cover"], 5, 5)
    assert green > 150 and red < 100
    assert with_cover["cover_url"] == f"{http.url}/dead-end.png"
    assert broken["cover"] == default["cover"]
