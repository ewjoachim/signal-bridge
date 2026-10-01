import re
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from babel import Locale, UnknownLocaleError
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DURATION_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def parse_duration(value: object) -> object:
    if isinstance(value, str) and (
        match := re.fullmatch(r"(\d+)([mhd])", value.strip())
    ):
        return timedelta(**{DURATION_UNITS[match[2]]: int(match[1])})
    return value


class Group(BaseModel):
    model_config = ConfigDict(frozen=True)

    group_id: str
    email: str
    name: str = ""
    freq: timedelta = timedelta(hours=12)
    locale: str = "en"
    reply_token: SecretStr

    _parse_freq = field_validator("freq", mode="before")(parse_duration)

    @field_validator("locale")
    @classmethod
    def check_locale(cls, value: str) -> str:
        try:
            Locale.parse(value)
        except UnknownLocaleError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @model_validator(mode="before")
    @classmethod
    def default_name(cls, data: object) -> object:
        if isinstance(data, dict) and not data.get("name") and "email" in data:
            return {**data, "name": str(data["email"]).partition("@")[0]}
        return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SIGNAL_BRIDGE_", env_nested_delimiter="__", frozen=True
    )

    account: str
    address: str
    admin_email: str

    imap_host: str
    imap_user: str
    imap_password: SecretStr
    smtp_host: str
    smtp_port: int = 465
    smtp_user: str
    smtp_password: SecretStr

    groups: dict[str, Group]

    data_dir: Path = Path("/data")
    timezone: ZoneInfo = ZoneInfo("UTC")
    poll_interval: timedelta = timedelta(minutes=2)

    _parse_poll_interval = field_validator("poll_interval", mode="before")(
        parse_duration
    )

    @property
    def signal_cli_dir(self) -> Path:
        return self.data_dir / "signal-cli"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bridge.db"

    def reply_address(self, group: Group) -> str:
        local, _, domain = self.address.partition("@")
        return f"{local}+{group.reply_token.get_secret_value()}@{domain}"
