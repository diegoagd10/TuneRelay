"""Navidrome-compatible MP4 tags written with mutagen."""

from pathlib import Path

from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

from tunerelay.store import Proposal

FREEFORM = "----:com.apple.iTunes:"
MBID_TAGS = {
    "recording": "MusicBrainz Track Id",
    "release": "MusicBrainz Album Id",
    "artist": "MusicBrainz Artist Id",
}


def _freeform(values: list[str]) -> list[MP4FreeForm]:
    return [MP4FreeForm(value.encode()) for value in values]


def write(audio: Path, proposal: Proposal) -> None:
    """Replace the file's tags with the proposal's metadata and embed its cover."""
    mp4 = MP4(audio)
    if mp4.tags is None:
        mp4.add_tags()
    tags = mp4.tags
    assert tags is not None  # noqa: S101 - just added
    tags.clear()
    tags["©nam"] = [proposal.title]
    tags["©ART"] = [proposal.artist]
    tags[FREEFORM + "ARTISTS"] = _freeform(proposal.artists or [proposal.artist])
    tags["aART"] = [proposal.album_artist]
    tags["©alb"] = [proposal.album]
    tags["trkn"] = [(proposal.track, proposal.track_total)]
    tags["disk"] = [(proposal.disc, proposal.disc_total)]
    tags["cpil"] = proposal.compilation
    if proposal.year is not None:
        tags["©day"] = [str(proposal.year)]
    if proposal.genre:
        tags["©gen"] = [proposal.genre]
    for kind, name in MBID_TAGS.items():
        mbid = proposal.mbids.get(kind)
        if mbid:
            tags[FREEFORM + name] = _freeform([mbid])
    if proposal.cover and Path(proposal.cover).exists():
        tags["covr"] = [MP4Cover(Path(proposal.cover).read_bytes(), imageformat=MP4Cover.FORMAT_JPEG)]
    mp4.save()  # pyright: ignore[reportUnknownMemberType] - mutagen's save() is untyped
