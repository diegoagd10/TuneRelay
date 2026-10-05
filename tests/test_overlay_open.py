"""The real overlay must accept shell-injected state before open() is delivered."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

QUICKSHELL = shutil.which("quickshell") or shutil.which("qs")
SHELL = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"


def test_the_shell_can_inject_the_service_and_open_the_overlay(tmp_path: Path) -> None:
    if QUICKSHELL is None or not (SHELL / "Commons").is_dir() or not os.environ.get("WAYLAND_DISPLAY"):
        pytest.skip("Quickshell, the Omarchy shell and a Wayland desktop are required")

    tests = Path(__file__).parent
    shutil.copyfile(tests / "qml" / "overlay_open_harness.qml", tmp_path / "shell.qml")
    for module in ("Commons", "Ui"):
        (tmp_path / module).symlink_to(SHELL / module)
    env = {
        **os.environ,
        "QT_QPA_PLATFORM": "wayland",
        "QT_FORCE_STDERR_LOGGING": "1",
        "TUNERELAY_TEST_OVERLAY": (tests.parent / "shell-plugin" / "dagd.tunerelay" / "Overlay.qml").as_uri(),
    }
    log = tmp_path / "quickshell.log"
    with (
        log.open("w") as capture,
        subprocess.Popen(
            [QUICKSHELL, "--no-color", "-p", str(tmp_path)],
            stdout=capture,
            stderr=subprocess.STDOUT,
            env=env,
        ) as process,
    ):
        try:
            for _ in range(100):
                if "RESULT " in log.read_text() or process.poll() is not None:
                    break
                time.sleep(0.05)
        finally:
            process.terminate()
            process.wait(timeout=5)
    output = log.read_text()
    lines = [line for line in output.splitlines() if "RESULT " in line]
    assert lines, output
    assert json.loads(lines[-1].split("RESULT ", 1)[1]) == [
        "opened=true",
        "service injected=true",
        "closed=false",
    ], output
