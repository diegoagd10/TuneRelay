"""Metadata proposals from `codex exec` with web search, filtered and ranked."""

import json
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from tunerelay import covers
from tunerelay.config import Config
from tunerelay.jsondata import JsonObject
from tunerelay.store import Proposal, YouTubeInfo

ORIGIN = "codex"
MAX_PROPOSALS = 3
MIN_CONFIDENCE = 0.5
ATTEMPTS = 2

NULLABLE_TEXT = {"type": ["string", "null"]}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposals"],
    "properties": {
        "proposals": {
            "type": "array",
            "maxItems": MAX_PROPOSALS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "artist",
                    "artists",
                    "album",
                    "album_artist",
                    "track",
                    "track_total",
                    "disc",
                    "disc_total",
                    "year",
                    "genre",
                    "compilation",
                    "mbids",
                    "confidence",
                    "sources",
                    "cover_url",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "artist": {"type": "string"},
                    "artists": {"type": "array", "items": {"type": "string"}},
                    "album": {"type": "string"},
                    "album_artist": {"type": "string"},
                    "track": {"type": "integer"},
                    "track_total": {"type": "integer"},
                    "disc": {"type": "integer"},
                    "disc_total": {"type": "integer"},
                    "year": {"type": ["integer", "null"]},
                    "genre": NULLABLE_TEXT,
                    "compilation": {"type": "boolean"},
                    "mbids": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["recording", "release", "artist"],
                        "properties": {
                            "recording": NULLABLE_TEXT,
                            "release": NULLABLE_TEXT,
                            "artist": NULLABLE_TEXT,
                        },
                    },
                    "confidence": {"type": "number"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "cover_url": NULLABLE_TEXT,
                },
            },
        }
    },
}

PROMPT = """\
Identify the song in this YouTube video and find its real release metadata.
Search the web (MusicBrainz, Discogs, Bandcamp, the artist's site, streaming stores).

Return up to {max} candidate releases, most likely first. For each give the
title, main artist, all credited artists, album, album artist, track number and
total, disc number and total, release year, genre, whether the album is a
compilation, MusicBrainz recording/release/artist IDs when you find them, a
confidence between 0 and 1, the URLs you used as sources, and a cover image URL
when you find one. If it is a standalone release, use "<Title> (Single)" as the
album with track 1/1. Never invent data: leave fields null rather than guess,
and return no proposals if you cannot identify the song.

YouTube title: {title}
Channel: {channel}
Duration: {duration}
Upload date: {upload_date}
Chapters: {chapters}
Description:
{description}
"""


def _duration(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def build_prompt(info: YouTubeInfo) -> str:
    return PROMPT.format(
        max=MAX_PROPOSALS,
        title=info.title,
        channel=info.channel,
        duration=_duration(info.duration),
        upload_date=info.upload_date or "unknown",
        chapters=", ".join(info.chapters) or "none",
        description=info.description.strip() or "(empty)",
    )


def _ask_codex(cfg: Config, prompt: str) -> str | None:
    with tempfile.TemporaryDirectory(prefix="tunerelay-codex-") as tmp:
        schema = Path(tmp) / "schema.json"
        schema.write_text(json.dumps(SCHEMA))
        output = Path(tmp) / "output.json"
        command = [
            cfg.tools.codex,
            "--search",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "-c",
            f'model_reasoning_effort="{cfg.codex_effort}"',
            "--output-schema",
            str(schema),
            "-o",
            str(output),
            "-",
        ]
        try:
            result = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=cfg.codex_timeout,
                cwd=tmp,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0 or not output.exists():
            return None
        return output.read_text()


def _parse(text: str) -> list[Proposal] | None:
    try:
        document = JsonObject.parse(text)
    except ValueError:
        return None
    return [
        replace(Proposal.from_json(item), origin=ORIGIN, cover=None) for item in document.objects("proposals")
    ]


def _usable(proposal: Proposal) -> bool:
    return bool(proposal.sources) and proposal.confidence >= MIN_CONFIDENCE and bool(proposal.title)


def resolve(cfg: Config, info: YouTubeInfo, folder: Path, fallback_cover: str | None) -> list[Proposal]:
    """Ask Codex (one retry), keep at most 3 sourced proposals with confidence >= 0.5, best first."""
    prompt = build_prompt(info)
    proposals: list[Proposal] | None = None
    for _ in range(ATTEMPTS):
        text = _ask_codex(cfg, prompt)
        proposals = _parse(text) if text is not None else None
        if proposals is not None:
            break
    kept = sorted(filter(_usable, proposals or []), key=lambda p: p.confidence, reverse=True)[:MAX_PROPOSALS]
    return [_with_cover(p, folder / f"cover-codex-{i}.jpg", fallback_cover) for i, p in enumerate(kept)]


def _with_cover(proposal: Proposal, dest: Path, fallback: str | None) -> Proposal:
    if proposal.cover_url:
        try:
            return replace(proposal, cover=str(covers.fetch(proposal.cover_url, dest)))
        except covers.CoverError:
            pass
    return replace(proposal, cover=fallback)
