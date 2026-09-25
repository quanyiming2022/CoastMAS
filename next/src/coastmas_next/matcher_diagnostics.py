"""Shared Coupler diagnostics: evidence and repairability do not collapse into one error."""

from typing import Literal

from pydantic import Field

from .contracts import Contract


class MatcherIssue(Contract):
    requirement: str
    candidate: str | None
    gate_type: Literal["input", "crs", "grid", "unit", "semantics", "permission", "implementation"]
    actual: object | None
    required: object
    severity: Literal["info", "warning", "error"]
    adaptable: bool
    suggested_adapter: str | None
    affected_node: str
    evidence: list[dict] = Field(default_factory=list)


def indicator_diagnostics(definition, matched, available):
    node = definition["indicator_id"]
    result = []
    if matched["status"] == "not_installed":
        result.append(
            MatcherIssue(
                requirement=node,
                candidate=None,
                gate_type="implementation",
                actual="not_installed",
                required="verified_runner",
                severity="error",
                adaptable=False,
                suggested_adapter=None,
                affected_node=node,
            )
        )
    for missing in matched["missing"]:
        result.append(
            MatcherIssue(
                requirement=missing,
                candidate=None,
                gate_type="input",
                actual=None,
                required=missing,
                severity="error",
                adaptable=False,
                suggested_adapter=None,
                affected_node=node,
            )
        )
    by_id = {a["id"]: a for a in available}
    for candidate in matched["candidates"]:
        if candidate["status"] == "adaptation":
            sources = [by_id[r["asset_id"]] for r in candidate["sources"]]
            result.append(
                MatcherIssue(
                    requirement="共同分析网格",
                    candidate=candidate["key"],
                    gate_type="grid",
                    actual=[
                        {k: a["facts"].get(k) for k in ("crs", "transform", "width", "height")}
                        for a in sources
                    ],
                    required="同一已确认的分析网格",
                    severity="warning",
                    adaptable=True,
                    suggested_adapter="align_grid",
                    affected_node=node,
                    evidence=[
                        {"asset_id": a["id"], "revision": a["revision"], "basis": "file_metadata"}
                        for a in sources
                    ],
                )
            )
        elif candidate["status"] == "inapplicable":
            a = by_id[candidate["sources"][0]["asset_id"]]
            gate = "crs" if not a["facts"].get("crs") else "semantics"
            result.append(
                MatcherIssue(
                    requirement=node,
                    candidate=candidate["key"],
                    gate_type=gate,
                    actual=a["facts"].get("crs")
                    if gate == "crs"
                    else "physical_reflectance_not_confirmed",
                    required="可靠坐标与物理反射率依据",
                    severity="error",
                    adaptable=False,
                    suggested_adapter=None,
                    affected_node=node,
                    evidence=[
                        {"asset_id": a["id"], "revision": a["revision"], "basis": "file_metadata"}
                    ],
                )
            )
        else:
            result.append(
                MatcherIssue(
                    requirement=node,
                    candidate=candidate["key"],
                    gate_type="input",
                    actual="satisfied",
                    required="fixed_input_roles",
                    severity="info",
                    adaptable=False,
                    suggested_adapter=None,
                    affected_node=node,
                    evidence=candidate["sources"],
                )
            )
    return [x.model_dump(mode="json") for x in result]
