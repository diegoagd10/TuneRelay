"""Desktop notifications (notify-send) and download progress in the Omarchy OSD."""

import contextlib
import subprocess

from tunerelay.config import Config

APP_NAME = "TuneRelay"
DOWNLOAD_ICON = "󰇚"


def _run(command: list[str]) -> None:
    # Notifications are best-effort and must never break the pipeline.
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(command, capture_output=True, timeout=10, check=False)


def send(cfg: Config, summary: str, body: str, *, critical: bool = False) -> None:
    command = [cfg.tools.notify, "--app-name", APP_NAME]
    if critical:
        command += ["--urgency", "critical"]
    _run([*command, summary, body])


def osd_progress(cfg: Config, percent: int) -> None:
    _run([cfg.tools.osd, "-i", DOWNLOAD_ICON, "-p", str(percent), "-d", "8000"])
