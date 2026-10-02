from typing import Annotated

import pydantic
from pydantic import alias_generators


def none_as_empty(value: object) -> object:
    return () if value is None else value


type Items[T] = Annotated[tuple[T, ...], pydantic.BeforeValidator(none_as_empty)]


class Model(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=alias_generators.to_camel, frozen=True, extra="ignore"
    )


class Mention(Model):
    start: int
    length: int
    number: str | None = None
    name: str | None = None
    uuid: str | None = None


class GroupInfo(Model):
    group_id: str | None = None
    group_name: str | None = None


class Attachment(Model):
    id: str | None = None
    content_type: str | None = None
    filename: str | None = None


class Quote(Model):
    author_uuid: str | None = None
    author_number: str | None = None
    text: str | None = None
    mentions: Items[Mention] = ()


class RemoteDelete(Model):
    timestamp: int


class DataMessage(Model):
    timestamp: int
    message: str | None = None
    group_info: GroupInfo | None = None
    mentions: Items[Mention] = ()
    attachments: Items[Attachment] = ()
    quote: Quote | None = None
    remote_delete: RemoteDelete | None = None


class EditMessage(Model):
    target_sent_timestamp: int
    data_message: DataMessage | None = None


class Envelope(Model):
    source_uuid: str | None = None
    source_name: str | None = None
    source_number: str | None = None
    data_message: DataMessage | None = None
    edit_message: EditMessage | None = None


class Received(Model):
    """One line of `signal-cli -o json receive`."""

    envelope: Envelope
