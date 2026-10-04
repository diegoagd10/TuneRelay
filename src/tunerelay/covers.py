"""Square cover images (centre crop) from thumbnails, URLs or local files."""

import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

HISTORY_SIZE = 256
MAX_DOWNLOAD = 20 * 1024 * 1024


class CoverError(Exception):
    """The image could not be fetched or decoded."""


def square(data: bytes, dest: Path, size: int | None = None) -> Path:
    """Centre-crop image bytes to a square JPEG, optionally downscaled to `size` pixels."""
    try:
        with Image.open(BytesIO(data)) as image:
            side = min(image.width, image.height)
            left = (image.width - side) // 2
            top = (image.height - side) // 2
            cropped = image.convert("RGB").crop((left, top, left + side, top + side))
    except (OSError, UnidentifiedImageError) as error:
        raise CoverError(f"not a usable image: {error}") from error
    if size is not None and side > size:
        cropped = cropped.resize((size, size), Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
    dest.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(dest, "JPEG", quality=92)
    return dest


def square_file(source: Path, dest: Path, size: int | None = None) -> Path:
    try:
        data = source.read_bytes()
    except OSError as error:
        raise CoverError(f"not a usable image: {error}") from error
    return square(data, dest, size)


def fetch(url: str, dest: Path) -> Path:
    """Download an http(s) image and store it as a square cover."""
    if not url.startswith(("http://", "https://")):
        raise CoverError(f"cover URL must be http(s): {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "TuneRelay"})  # noqa: S310 - scheme checked above
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - scheme checked above
            data = response.read(MAX_DOWNLOAD + 1)
    except OSError as error:
        raise CoverError(f"could not download {url}: {error}") from error
    if len(data) > MAX_DOWNLOAD:
        raise CoverError(f"cover at {url} is too large")
    return square(data, dest)
