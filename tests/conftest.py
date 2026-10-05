"""Test harness: drives the real `tunerelay` executables against fakes.

Tests only talk to TuneRelay the way the browser and the Omarchy plugin do:
native messaging frames on stdin, CLI commands with JSON output, and files on
disk. External tools are replaced by the executables in `tests/fakes/`.
"""

import json
import os
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

FAKES = Path(__file__).parent / "fakes"
BIN = Path(sys.executable).parent


def _toml_value(value: str | int | float | list[str]) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(v) for v in value) + "]"
    if isinstance(value, str):
        return json.dumps(value)
    return str(value)


@dataclass
class TuneRelay:
    root: Path
    env: dict[str, str] = field(default_factory=dict[str, str])
    config: dict[str, dict[str, str | int | float | list[str]]] = field(
        default_factory=dict[str, dict[str, str | int | float | list[str]]]
    )

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def inbox(self) -> Path:
        return self.home / "inbox"

    @property
    def library(self) -> Path:
        return self.root / "library"

    @property
    def log(self) -> Path:
        return self.root / "fake.log"

    def configure(self, section: str, **values: str | int | float | list[str]) -> None:
        self.config.setdefault(section, {}).update(values)
        lines: list[str] = []
        for name, entries in self.config.items():
            lines.append(f"[{name}]")
            lines.extend(f"{key} = {_toml_value(value)}" for key, value in entries.items())
            lines.append("")
        (self.home / "config.toml").write_text("\n".join(lines))

    def run(self, *args: str, stdin: bytes = b"", timeout: float = 30) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [str(BIN / "tunerelay"), *args],
            input=stdin,
            capture_output=True,
            env=self.env,
            timeout=timeout,
            check=False,
        )

    def cli(self, *args: str) -> dict:
        result = self.run(*args)
        assert result.returncode == 0, result.stderr.decode() + result.stdout.decode()
        return json.loads(result.stdout)

    def cli_error(self, *args: str) -> str:
        result = self.run(*args)
        assert result.returncode != 0, result.stdout.decode()
        return json.loads(result.stdout)["error"]

    def daemon_once(self) -> None:
        result = self.run("daemon", "--once", timeout=60)
        assert result.returncode == 0, result.stderr.decode()

    def host(self, message: dict) -> dict:
        payload = json.dumps(message).encode()
        return self.host_raw(struct.pack("<I", len(payload)) + payload)

    def host_raw(self, frame: bytes) -> dict:
        result = subprocess.run(
            [str(BIN / "tunerelay-host"), "chrome-extension://abc/"],
            input=frame,
            capture_output=True,
            env=self.env,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode()
        (length,) = struct.unpack("<I", result.stdout[:4])
        return json.loads(result.stdout[4 : 4 + length])

    def calls(self, tool: str) -> list[dict]:
        if not self.log.exists():
            return []
        entries = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [entry for entry in entries if entry["tool"] == tool]

    def notifications(self) -> list[str]:
        return [" | ".join(call["args"][-2:]) for call in self.calls("notify-send")]

    def song(self, song_id: int) -> dict:
        return self.cli("show", str(song_id))

    def wait_for_state(self, song_id: int, state: str, timeout: float = 15) -> dict:
        def reached() -> bool:
            return self.song(song_id)["state"] == state

        wait_until(reached, timeout)
        return self.song(song_id)

    def capture(self, video_id: str = "dQw4w9WgXcQ") -> int:
        """Capture through the native host and wait until the download is queued."""
        reply = self.host({"url": f"https://www.youtube.com/watch?v={video_id}"})
        assert reply["status"] == "accepted", reply
        self.wait_for_state(reply["song"]["id"], "queued")
        return reply["song"]["id"]

    def codex_returns(self, proposals: list[dict]) -> None:
        path = self.root / "codex-output.json"
        path.write_text(json.dumps({"proposals": proposals}))
        self.env["FAKE_CODEX_OUTPUT"] = str(path)

    def ready_for_review(self, video_id: str = "dQw4w9WgXcQ") -> int:
        song_id = self.capture(video_id)
        self.daemon_once()
        assert self.song(song_id)["state"] == "ready_for_review"
        return song_id


def rgb(image: str | Path, x: int, y: int) -> tuple[int, int, int]:
    """The RGB colour of one pixel of an image file."""
    with Image.open(image) as opened:
        pixel = opened.convert("RGB").getpixel((x, y))
    assert isinstance(pixel, tuple)
    return (int(pixel[0]), int(pixel[1]), int(pixel[2]))


def wait_until(predicate: Callable[[], bool], timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        time.sleep(0.05)


@pytest.fixture
def tr(tmp_path: Path) -> Iterator[TuneRelay]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("notify-send", "omarchy-osd", "mpv", "pass"):
        (bin_dir / name).symlink_to(FAKES / "recorder")
    env = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(("COVERAGE", "PATH", "HOME", "LANG", "PYTHON")) or key == "LC_ALL"
    }
    env["TUNERELAY_HOME"] = str(tmp_path / "home")
    env["FAKE_LOG"] = str(tmp_path / "fake.log")
    harness = TuneRelay(root=tmp_path, env=env)
    harness.home.mkdir()
    harness.library.mkdir()
    harness.configure(
        "tools",
        ytdlp=str(FAKES / "yt-dlp"),
        codex=str(FAKES / "codex"),
        notify=str(bin_dir / "notify-send"),
        osd=str(bin_dir / "omarchy-osd"),
        player=str(bin_dir / "mpv"),
        ssh=str(FAKES / "ssh"),
        rsync=str(FAKES / "rsync"),
        password=str(bin_dir / "pass"),
    )
    harness.configure("codex", timeout=5)
    harness.configure("delivery", transport="local", local_root=str(harness.library), retry_interval=0.05)
    harness.configure("scan", method="none")
    yield harness


@dataclass
class FakeHttp:
    """A local HTTP server standing in for image hosts and Navidrome; it records every request."""

    url: str
    files: dict[str, bytes] = field(default_factory=dict[str, bytes])
    requests: list[str] = field(default_factory=list[str])
    status: int = 200


@pytest.fixture
def http() -> Iterator[FakeHttp]:
    fake = FakeHttp(url="")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            fake.requests.append(self.path)
            body = fake.files.get(self.path.split("?")[0], b'{"subsonic-response": {"status": "ok"}}')
            self.send_response(fake.status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    fake.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield fake
    server.shutdown()
