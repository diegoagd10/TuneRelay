"""The deterministic default proposal, built from YouTube data before any AI runs."""

import re

from tunerelay.store import Proposal, YouTubeInfo

ORIGIN = "youtube-default"
CHANNEL_SUFFIXES = re.compile(r"(\s*-\s*Topic|\s*VEVO|\s+Official)$", re.IGNORECASE)
ARTIST_TITLE = re.compile(r"^(?P<artist>.+?)\s+[-\u2013\u2014]\s+(?P<title>.+)$")  # hyphen, en or em dash


def clean_channel(channel: str) -> str:
    previous = None
    while previous != channel:
        previous, channel = channel, CHANNEL_SUFFIXES.sub("", channel).strip()
    return channel


def default_proposal(info: YouTubeInfo, url: str, cover: str | None) -> Proposal:
    match = ARTIST_TITLE.match(info.title.strip())
    title = match.group("title").strip() if match else info.title.strip()
    artist = clean_channel(info.channel) or (match.group("artist").strip() if match else "")
    year = int(info.upload_date[:4]) if info.upload_date[:4].isdigit() else None
    return Proposal(
        origin=ORIGIN,
        title=title,
        artist=artist,
        artists=[artist] if artist else [],
        album=f"{title} (Single)",
        album_artist=artist,
        track=1,
        track_total=1,
        disc=1,
        disc_total=1,
        year=year,
        genre=None,
        compilation=False,
        mbids={},
        confidence=0.0,
        sources=[url] if url else [],
        cover=cover,
    )
