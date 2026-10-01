from datetime import timedelta

import pytest

from signal_bridge.config import Settings

BASE_ENV = {
    "SIGNAL_BRIDGE_ACCOUNT": "+33100000000",
    "SIGNAL_BRIDGE_ADDRESS": "bridge@example.org",
    "SIGNAL_BRIDGE_ADMIN_EMAIL": "admin@example.org",
    "SIGNAL_BRIDGE_IMAP_HOST": "mail.example.org",
    "SIGNAL_BRIDGE_IMAP_USER": "bridge",
    "SIGNAL_BRIDGE_IMAP_PASSWORD": "pw",
    "SIGNAL_BRIDGE_SMTP_HOST": "mail.example.org",
    "SIGNAL_BRIDGE_SMTP_USER": "bridge",
    "SIGNAL_BRIDGE_SMTP_PASSWORD": "pw",
    "SIGNAL_BRIDGE_TIMEZONE": "Europe/Paris",
    "SIGNAL_BRIDGE_GROUPS__BAND__GROUP_ID": "abc=",
    "SIGNAL_BRIDGE_GROUPS__BAND__EMAIL": "marie@example.org",
    "SIGNAL_BRIDGE_GROUPS__BAND__NAME": "Marie",
    "SIGNAL_BRIDGE_GROUPS__BAND__FREQ": "1d",
    "SIGNAL_BRIDGE_GROUPS__BAND__REPLY_TOKEN": "tok1",
    "SIGNAL_BRIDGE_GROUPS__TEST_GROUP__GROUP_ID": "def=",
    "SIGNAL_BRIDGE_GROUPS__TEST_GROUP__EMAIL": "test@example.org",
    "SIGNAL_BRIDGE_GROUPS__TEST_GROUP__REPLY_TOKEN": "tok2",
}


@pytest.fixture
def settings(monkeypatch) -> Settings:
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    return Settings()


def test_groups(settings):
    assert set(settings.groups) == {"band", "test_group"}
    band, test = settings.groups["band"], settings.groups["test_group"]
    assert (band.name, band.freq) == ("Marie", timedelta(days=1))
    assert (test.name, test.freq) == ("test", timedelta(hours=12))


def test_reply_address(settings):
    assert settings.reply_address(settings.groups["band"]) == "bridge+tok1@example.org"


def test_paths(settings):
    assert str(settings.signal_cli_dir) == "/data/signal-cli"
    assert str(settings.db_path) == "/data/bridge.db"
