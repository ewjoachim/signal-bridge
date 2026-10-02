import json

import pydantic

from signal_bridge import __main__ as bridge_main
from signal_bridge import config

from . import conftest


class FakeSignal:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def receive(self) -> list[str]:
        return self.lines


def make_bridge(
    tmp_path, group: config.Group, *, alert_on_unparsed: bool = True
) -> bridge_main.Bridge:
    settings = config.Settings(
        account=conftest.ACCOUNT,
        address="bridge@example.org",
        admin_email="admin@example.org",
        imap_host="mail.example.org",
        imap_user="bridge",
        imap_password=pydantic.SecretStr("pw"),
        smtp_host="mail.example.org",
        smtp_user="bridge",
        smtp_password=pydantic.SecretStr("pw"),
        groups={"band": group},
        data_dir=tmp_path,
        alert_on_unparsed=alert_on_unparsed,
    )
    return bridge_main.Bridge(settings)


def test_bad_envelope_is_saved_and_others_processed(tmp_path, monkeypatch, group):
    monkeypatch.setattr(bridge_main, "HEARTBEAT", tmp_path / "heartbeat")
    sent = []
    monkeypatch.setattr(
        bridge_main.mail, "send", lambda settings, msg: sent.append(msg)
    )
    bridge = make_bridge(tmp_path, group)
    good = json.dumps(conftest.envelope(conftest.group_data(message="still here")))
    bad_shape = json.dumps(
        conftest.envelope(conftest.group_data(mentions=[{"start": "x"}]))
    )
    bridge.signal = FakeSignal(["not json", bad_shape, good])  # ty: ignore[invalid-assignment]

    bridge.receive()

    assert [m.text for m in bridge.store.pending(conftest.GROUP_ID)] == ["still here"]
    assert (tmp_path / "unparsed.jsonl").read_text().splitlines() == [
        "not json",
        bad_shape,
    ]
    assert (tmp_path / "heartbeat").exists()
    [alert] = sent
    assert alert["To"] == "admin@example.org"
    assert alert["Subject"] == "signal-bridge could not process 2 envelope(s)"
    assert bad_shape in alert.get_content()


def test_unparsed_alert_can_be_disabled(tmp_path, monkeypatch, group):
    monkeypatch.setattr(bridge_main, "HEARTBEAT", tmp_path / "heartbeat")
    sent = []
    monkeypatch.setattr(
        bridge_main.mail, "send", lambda settings, msg: sent.append(msg)
    )
    bridge = make_bridge(tmp_path, group, alert_on_unparsed=False)
    bridge.signal = FakeSignal(["not json"])  # ty: ignore[invalid-assignment]

    bridge.receive()

    assert sent == []
    assert (tmp_path / "unparsed.jsonl").read_text() == "not json\n"
