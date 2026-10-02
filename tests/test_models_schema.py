"""Our hand-written models must stay compatible with signal-cli's published JSON schemas."""

import json
import os
import pathlib
import re
import tarfile
import types
import typing
import urllib.error
import urllib.request

import pydantic
import pytest

from signal_bridge import models

DOCKERFILE = pathlib.Path(__file__).parent.parent / "Dockerfile"
SCHEMAS: dict[type[pydantic.BaseModel], str] = {
    models.Envelope: "message-envelope",
    models.DataMessage: "data-message",
    models.EditMessage: "edit-message",
    models.GroupInfo: "group-info",
    models.Mention: "mention",
    models.Attachment: "attachment",
    models.Quote: "quote",
    models.RemoteDelete: "remote-delete",
}
PRIMITIVES: dict[object, str] = {str: "string", int: "integer", bool: "boolean"}


@pytest.fixture(scope="session")
def schemas(pytestconfig: pytest.Config) -> dict[str, dict]:
    match = re.search(
        r"^ARG SIGNAL_CLI_VERSION=(\S+)$", DOCKERFILE.read_text(), re.MULTILINE
    )
    assert match, "SIGNAL_CLI_VERSION not found in the Dockerfile"
    version = match[1]
    directory = pytestconfig.cache.mkdir(f"signal-cli-schemas-{version}")
    if not any(directory.glob("*.schema.json")):
        url = f"https://github.com/AsamK/signal-cli/releases/download/v{version}/signal-cli-{version}-json-schemas.tar.gz"
        archive = directory / "schemas.tar.gz"
        try:
            urllib.request.urlretrieve(url, archive)
        except urllib.error.URLError:
            if os.environ.get("CI"):
                raise
            pytest.skip("signal-cli JSON schemas unavailable (offline?)")
        with tarfile.open(archive) as tar:
            tar.extractall(directory, filter="data")
    return {
        path.name.removesuffix(".schema.json"): json.loads(path.read_text())
        for path in directory.rglob("*.schema.json")
    }


def schema_type(annotation: object) -> dict:
    """The JSON-schema fragment a field annotation corresponds to (Optional unwrapped)."""
    if isinstance(alias := typing.get_origin(annotation), typing.TypeAliasType):
        annotation = alias.__value__[typing.get_args(annotation)]
    if typing.get_origin(annotation) is typing.Annotated:
        annotation = typing.get_args(annotation)[0]
    if typing.get_origin(annotation) in {typing.Union, types.UnionType}:
        (annotation,) = [
            arg for arg in typing.get_args(annotation) if arg is not type(None)
        ]
    if typing.get_origin(annotation) is tuple:
        return {"type": "array", "items": schema_type(typing.get_args(annotation)[0])}
    if isinstance(annotation, type) and issubclass(annotation, pydantic.BaseModel):
        return {"$ref": f"{SCHEMAS[annotation]}.schema.json"}
    return {"type": PRIMITIVES[annotation]}


@pytest.mark.parametrize("model", SCHEMAS, ids=lambda model: model.__name__)
def test_model_matches_signal_cli_schema(
    model: type[pydantic.BaseModel], schemas: dict[str, dict]
):
    schema = schemas[SCHEMAS[model]]
    for name, field in model.model_fields.items():
        alias = field.alias or name
        assert alias in schema["properties"], (
            f"{model.__name__}.{name}: no {alias!r} in the schema"
        )
        expected = schema_type(field.annotation)
        actual = {
            key: value
            for key, value in schema["properties"][alias].items()
            if key in expected
        }
        assert actual == expected, f"{model.__name__}.{name}: type mismatch"
        if field.is_required():
            assert alias in schema.get("required", []), (
                f"{model.__name__}.{name}: required here but optional in the schema"
            )
