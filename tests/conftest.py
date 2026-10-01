import pytest
from pydantic import SecretStr

from signal_bridge.config import Group

ACCOUNT = "+33199000000"
GROUP_ID = "Z3JvdXAtaWQ="


@pytest.fixture
def group() -> Group:
    return Group(
        group_id=GROUP_ID, email="marie@example.org", reply_token=SecretStr("s3cret")
    )


def envelope(data_message: dict | None = None, **extra: object) -> dict:
    env = {
        "source": "+33639980001",
        "sourceNumber": "+33639980001",
        "sourceUuid": "uuid-paul",
        "sourceName": "Paul",
        "sourceDevice": 1,
        "timestamp": 1_790_000_000_000,
        "serverReceivedTimestamp": 1_790_000_000_100,
        "serverDeliveredTimestamp": 1_790_000_000_200,
        **extra,
    }
    if data_message is not None:
        env["dataMessage"] = data_message
    return {"envelope": env, "account": ACCOUNT}


def group_data(**fields: object) -> dict:
    return {
        "timestamp": 1_790_000_000_000,
        "groupInfo": {
            "groupId": GROUP_ID,
            "groupName": "The Band",
            "revision": 3,
            "type": "DELIVER",
        },
        **fields,
    }
