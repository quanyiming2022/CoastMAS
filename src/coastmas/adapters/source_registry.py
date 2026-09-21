"""Trusted connector catalog; application requests can only select registered identities."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from coastmas.adapters.source_connectors import HTTPSource, PostgreSQLSource, Source
from coastmas.configuration import configuration_value
from coastmas.core.contracts import Contract, Name, Version


@dataclass(frozen=True)
class RegisteredSource:
    label: str
    projects: frozenset[str]
    revision: int
    source: Source

    @property
    def kind(self) -> Literal["http", "postgresql"]:
        return "http" if isinstance(self.source, HTTPSource) else "postgresql"


def load_sources(path: Path | None) -> dict[str, RegisteredSource]:
    if path is None:
        return {}
    try:
        if path.stat().st_mode & 0o077:
            raise RuntimeError("source configuration requires private file permissions (0600)")
        with path.open("rb") as stream:
            content = stream.read(262145)
        if len(content) > 262144:
            raise RuntimeError("source configuration exceeds file budget")
        values = SOURCE_CONFIG.validate_python(json.loads(content, object_pairs_hook=unique_keys))
        registered: dict[str, RegisteredSource] = {}
        for identifier, spec in values.items():
            source: Source
            if isinstance(spec, HTTPConfiguration):
                source = HTTPSource(
                    url=spec.url,
                    allow_private=spec.allow_private,
                    headers={
                        header: configuration_value(env) for header, env in spec.headers_env.items()
                    },
                )
            else:
                source = PostgreSQLSource(
                    dsn=configuration_value(spec.dsn_env),
                    schema=spec.schema_name,
                    table=spec.table,
                    columns=spec.columns,
                    order_by=spec.order_by,
                )
            registered[identifier] = RegisteredSource(
                label=spec.name, projects=spec.projects, revision=spec.revision, source=source
            )
        return registered
    except RuntimeError:
        raise
    except (OSError, ValueError, RecursionError):
        raise RuntimeError("invalid data source configuration") from None


class ConnectorConfiguration(Contract):
    name: Name
    revision: Version
    projects: frozenset[Name] = Field(min_length=1, max_length=1000)


class HTTPConfiguration(ConnectorConfiguration):
    kind: Literal["http"]
    url: str = Field(min_length=1, max_length=4096, repr=False)
    allow_private: bool = Field(default=False, strict=True)
    headers_env: dict[str, Name] = Field(default_factory=dict, max_length=2)


class DatabaseConfiguration(ConnectorConfiguration):
    kind: Literal["postgresql"]
    dsn_env: Name
    schema_name: Name = Field(alias="schema")
    table: Name
    columns: tuple[Name, ...] = Field(min_length=1, max_length=64)
    order_by: tuple[Name, ...] = Field(min_length=1, max_length=64)


SOURCE_CONFIG = TypeAdapter(
    dict[Name, Annotated[HTTPConfiguration | DatabaseConfiguration, Field(discriminator="kind")]]
)


def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate configuration key")
        output[key] = value
    return output
