import datetime
import pathlib
import re
import zoneinfo
from typing import Annotated

import babel
import pydantic
import pydantic_settings

DURATION_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def parse_duration(value: object) -> object:
    if isinstance(value, str) and (
        match := re.fullmatch(r"(\d+)([mhd])", value.strip())
    ):
        return datetime.timedelta(**{DURATION_UNITS[match[2]]: int(match[1])})
    return value


def check_locale(value: str) -> str:
    try:
        babel.Locale.parse(value)
    except babel.UnknownLocaleError as exc:
        raise ValueError(str(exc)) from exc
    return value


type Duration = Annotated[datetime.timedelta, pydantic.BeforeValidator(parse_duration)]
type LocaleName = Annotated[str, pydantic.AfterValidator(check_locale)]


class Group(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)

    group_id: str
    email: str
    name: str = ""
    freq: Duration = datetime.timedelta(hours=12)
    locale: LocaleName = "en"
    reply_token: pydantic.SecretStr

    @pydantic.model_validator(mode="before")
    @classmethod
    def default_name(cls, data: object) -> object:
        if isinstance(data, dict) and not data.get("name") and "email" in data:
            return {**data, "name": str(data["email"]).partition("@")[0]}
        return data


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(
        env_prefix="SIGNAL_BRIDGE_", env_nested_delimiter="__", frozen=True
    )

    account: str
    address: str
    admin_email: str
    alert_on_unparsed: bool = True

    imap_host: str
    imap_user: str
    imap_password: pydantic.SecretStr
    smtp_host: str
    smtp_port: int = 465
    smtp_user: str
    smtp_password: pydantic.SecretStr

    groups: dict[str, Group]

    data_dir: pathlib.Path = pathlib.Path("/data")
    timezone: zoneinfo.ZoneInfo = zoneinfo.ZoneInfo("UTC")
    poll_interval: Duration = datetime.timedelta(minutes=2)

    @property
    def signal_cli_dir(self) -> pathlib.Path:
        return self.data_dir / "signal-cli"

    @property
    def db_path(self) -> pathlib.Path:
        return self.data_dir / "bridge.db"

    @property
    def unparsed_path(self) -> pathlib.Path:
        return self.data_dir / "unparsed.jsonl"

    def reply_address(self, group: Group) -> str:
        local, _, domain = self.address.partition("@")
        return f"{local}+{group.reply_token.get_secret_value()}@{domain}"
