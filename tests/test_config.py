import tomllib

from conftest import TuneRelay
from test_delivery import confirmed


def test_the_first_run_writes_a_commented_config_without_server_values(tr: TuneRelay) -> None:
    (tr.home / "config.toml").unlink()

    tr.cli("status")

    text = (tr.home / "config.toml").read_text()
    config = tomllib.loads(text)
    assert config["delivery"]["transport"] == "ssh"
    assert config["delivery"]["hosts"] == []
    assert config["delivery"]["music_dir"] == ""
    assert config["scan"]["method"] == "subsonic"
    assert config["scan"]["password_entry"] == ""
    assert "# " in text


def test_an_unknown_transport_fails_delivery_with_a_clear_error(tr: TuneRelay) -> None:
    tr.configure("delivery", transport="ftp")
    song_id = confirmed(tr)

    tr.daemon_once()

    assert tr.song(song_id)["error"] == 'delivery.transport must be "ssh" or "local", not "ftp"'


def test_a_missing_library_folder_fails_delivery(tr: TuneRelay) -> None:
    tr.configure("delivery", local_root=str(tr.root / "nowhere"))
    song_id = confirmed(tr)

    tr.daemon_once()

    assert tr.song(song_id)["error"] == f"library folder {tr.root / 'nowhere'} does not exist"


def test_incomplete_scan_settings_are_reported_after_a_successful_delivery(tr: TuneRelay) -> None:
    tr.configure("scan", method="subsonic", url="", user="dagd", password_entry="")
    song_id = confirmed(tr)

    tr.daemon_once()

    assert tr.song(song_id)["state"] == "sent"
    assert (
        tr.notifications()[-1]
        == "Navidrome scan failed | config.toml is missing scan.url, scan.password_entry"
    )


def test_an_unknown_scan_method_is_reported(tr: TuneRelay) -> None:
    tr.configure("scan", method="webhook")
    confirmed(tr)

    tr.daemon_once()

    assert (
        tr.notifications()[-1]
        == 'Navidrome scan failed | scan.method must be "subsonic" or "none", not "webhook"'
    )


def test_an_unreadable_password_is_reported(tr: TuneRelay) -> None:
    tr.configure("scan", method="subsonic", url="http://127.0.0.1:9", user="dagd", password_entry="navidrome")
    tr.env["FAKE_PASS_FAIL"] = "1"
    confirmed(tr)

    tr.daemon_once()

    assert (
        tr.notifications()[-1]
        == "Navidrome scan failed | could not read the password from pass entry navidrome"
    )


def test_a_malformed_config_is_reported_as_a_json_error(tr: TuneRelay) -> None:
    (tr.home / "config.toml").write_text("[delivery\ntransport = 'ssh'\n")

    assert tr.cli_error("status").startswith("config.toml is not valid TOML")


def test_an_unusable_database_is_reported_as_a_json_error(tr: TuneRelay) -> None:
    (tr.home / "tunerelay.db").write_text("this is not a database" * 100)

    assert tr.cli_error("status").startswith("cannot open the TuneRelay database")
