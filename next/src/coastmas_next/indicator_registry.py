"""Versioned built-in recipes. User selection never authors an execution contract."""

import copy
import hashlib
import json
from pathlib import Path

from .store import Problem

ROOT = Path(__file__).parent
CATALOG = ROOT / "builtin_indicators.json"


def definitions():
    return json.loads(CATALOG.read_text())


def require_definition(indicator_id, version=None):
    matches = [
        r
        for r in definitions()
        if r["indicator_id"] == indicator_id and (version is None or r["version"] == version)
    ]
    if not matches:
        raise Problem(404, "INDICATOR_UNKNOWN", "此指标版本不可用")
    item = max(matches, key=lambda r: r["version"])
    if item["status"] != "published":
        raise Problem(422, "INDICATOR_NOT_INSTALLED", "此指标尚未安装可执行实现")
    actual = hashlib.sha256((ROOT / "indicator_kernels_v1.py").read_bytes()).hexdigest()
    if actual != item["implementation_sha256"]:
        raise Problem(409, "INDICATOR_CODE_CHANGED", "指标实现与已验证版本不一致，请重新验证发布")
    return copy.deepcopy(item)


def validate_parameters(definition, supplied):
    from jsonschema import Draft202012Validator

    parameters = {**definition["default_parameters"], **supplied}
    errors = list(Draft202012Validator(definition["parameters_schema"]).iter_errors(parameters))
    if errors:
        raise Problem(
            422,
            "INDICATOR_PARAMETERS",
            "指标业务参数不在已验证范围内",
            {"fields": [".".join(map(str, e.path)) for e in errors]},
        )
    return parameters
