"""Bounded metadata import/export; imported execution and validation claims are untrusted."""

import json
from typing import Literal

import yaml  # type: ignore[import-untyped]
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode  # type: ignore[import-untyped]
from yaml.tokens import AliasToken, AnchorToken  # type: ignore[import-untyped]

from coastmas.core.contracts import ModelSpec
from coastmas.core.errors import ConstraintError

Format = Literal["json", "yaml"]


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ConstraintError("duplicate key in model document")
        result[key] = value
    return result


def validate_yaml_node(node: Node, depth: int = 0) -> None:
    if depth > 64:
        raise ConstraintError("model document nesting budget exceeded")
    if isinstance(node, MappingNode):
        keys: set[str] = set()
        for key, value in node.value:
            if not isinstance(key, ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                raise ConstraintError("model document mapping keys must be strings")
            if key.value in keys:
                raise ConstraintError("duplicate key in model document")
            keys.add(key.value)
            validate_yaml_node(value, depth + 1)
    elif isinstance(node, SequenceNode):
        for value in node.value:
            validate_yaml_node(value, depth + 1)


def reject_embedded_credentials(value: object, depth: int = 0) -> None:
    if depth > 64:
        raise ConstraintError("model configuration nesting budget exceeded")
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in {
                "password",
                "api_key",
                "access_token",
                "secret_key",
                "authorization",
            }:
                raise ConstraintError(
                    "runtime credentials require a server-side credential reference"
                )
            reject_embedded_credentials(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            reject_embedded_credentials(child, depth + 1)


def import_model(content: str, format: Format) -> ModelSpec:
    if len(content.encode("utf-8")) > 262144:
        raise ConstraintError("model document byte budget exceeded")
    raw: object
    try:
        if format == "json":
            raw = json.loads(content, object_pairs_hook=unique_object)
        elif format == "yaml":
            if any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(content)):
                raise ConstraintError("YAML aliases and anchors are not accepted")
            document = yaml.compose(content)
            if document is None:
                raise ConstraintError("model document is empty")
            validate_yaml_node(document)
            raw = yaml.safe_load(content)
        else:
            raise ConstraintError("unsupported model document format")
    except (json.JSONDecodeError, yaml.YAMLError, RecursionError) as exc:
        raise ConstraintError("model document is not valid bounded JSON or safe YAML") from exc
    model = ModelSpec.model_validate(raw)
    reject_embedded_credentials(model.runtime_config)
    return model.model_copy(
        update={"validation_status": "UNVALIDATED", "execution_status": "NOT_EXECUTABLE"}
    )


def export_model(model: ModelSpec, format: Format) -> str:
    reject_embedded_credentials(model.runtime_config)
    payload = model.model_dump(mode="json")
    if format == "json":
        return (
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + "\n"
        )
    if format == "yaml":
        return str(yaml.safe_dump(payload, allow_unicode=True, sort_keys=True))
    raise ConstraintError("unsupported model document format")
