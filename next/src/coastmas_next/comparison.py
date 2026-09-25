"""Compare immutable scientific results only within a declared common basis."""

import math

from coastmas.core.contracts import UNITS


def source_signature(result):
    manifest = result["manifest"]
    assets = {a["id"]: a["sha256"] for a in manifest["assets"]}
    return sorted(
        (assets.get(ref["asset_id"]), ref.get("layer") or "")
        for ref in manifest["draft"]["selection"]
    )


def mapping_signature(result):
    manifest = result["manifest"]
    assets = {a["id"]: a["sha256"] for a in manifest["assets"]}
    return sorted(
        (
            assets.get(b["asset_id"]),
            b["field"],
            b.get("role"),
            b.get("concept") or "",
            b.get("unit") or "",
            b.get("support") or "",
            b.get("template_id") or "",
            b.get("template_revision") or 0,
        )
        for b in manifest["draft"]["mapping"]
        if b.get("role") != "ignored"
    )


def compare(left, right):
    """A blocked comparison still explains differences; it never invents rankings."""
    report = {
        "comparable": False,
        "mode": "same_basis",
        "issues": [],
        "differences": [],
        "adaptations": [],
        "rows": [],
        "business_validated": False,
        "policy_decision": False,
        "scope": "immutable_result_comparison",
        "difference_direction": "right_minus_left",
        "basis": "同一不可变资料与语义绑定；这是计算结果比较，不代表真实变化或政策决定。",
    }

    def issue(code, message):
        report["issues"].append({"code": code, "message": message})

    def difference(field, a, b):
        if a != b:
            report["differences"].append({"field": field, "left": a, "right": b})

    def number(value):
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
        ):
            raise ValueError("invalid result number")
        return value

    def conversion(value, source, target):
        try:
            converted = float(UNITS.Quantity(number(value), source).to(target).magnitude)
            number(converted)
        except Exception:
            issue("UNIT_UNKNOWN", "成果或方法单位未知、不相容，或数值无效；不能自动比较。")
            return None
        if source != target and not any(
            x["from_unit"] == source and x["to_unit"] == target for x in report["adaptations"]
        ):
            report["adaptations"].append(
                {
                    "from_unit": source,
                    "to_unit": target,
                    "rule": "quantity_conversion",
                    "loss": "float64_roundoff",
                }
            )
        return converted

    def aligned(a, b, key):
        ids_a, ids_b = [r[key] for r in a], [r[key] for r in b]
        if (
            len(a) > 100000
            or len(b) > 100000
            or not a
            or not b
            or any(not isinstance(i, str) or not i for i in ids_a + ids_b)
            or len(set(ids_a)) != len(a)
            or len(set(ids_b)) != len(b)
        ):
            issue("IDENTITY_INVALID", "成果标识为空、重复或超过当前100000行比较范围。")
            return []
        if set(ids_a) != set(ids_b):
            issue("IDENTITY_DIFFERENT", "两份成果的观测或单元集合不同；不能按行号强行对齐。")
            return []
        index = {r[key]: r for r in b}
        return [(r, index[r[key]]) for r in a]

    left_kind = left["manifest"]["draft"]["purpose"]
    right_kind = right["manifest"]["draft"]["purpose"]
    difference("purpose", left_kind, right_kind)
    if left_kind != right_kind:
        issue("PURPOSE_DIFFERENT", "成果业务类型不同，不能计算数值差异。")
    if source_signature(left) != source_signature(right):
        issue("SOURCE_DIFFERENT", "资料哈希或图层不同；跨批次、时期与空间范围尚未建立可比依据。")
    if mapping_signature(left) != mapping_signature(right):
        issue("MAPPING_DIFFERENT", "变量、单位、支撑或科学定义版本不同，需要先核对解释。")
    a, b = left["data"], right["data"]
    difference("scope", a.get("scope"), b.get("scope"))
    if a.get("scope") != b.get("scope"):
        issue("SCOPE_DIFFERENT", "样本、全域或观测支撑范围不同。")
    if left_kind != right_kind:
        return report
    try:
        if left_kind == "assessment":
            ca = left["manifest"]["method"]["spec"]["configuration"]
            cb = right["manifest"]["method"]["spec"]["configuration"]
            difference("method", ca["method"], cb["method"])
            if ca["method"] != cb["method"]:
                issue("METHOD_DIFFERENT", "评价方法不同，评分尺度不等价；不计算分差或合并排名。")
            indicators = aligned(ca["indicators"], cb["indicators"], "concept")
            for ia, ib in indicators:
                low = conversion(ib["lower"], ib["unit"], ia["unit"])
                high = conversion(ib["upper"], ib["unit"], ia["unit"])
                if (
                    low is not None
                    and not math.isclose(low, number(ia["lower"]), rel_tol=1e-12, abs_tol=1e-12)
                    or high is not None
                    and not math.isclose(high, number(ia["upper"]), rel_tol=1e-12, abs_tol=1e-12)
                    or ia["positive"] != ib["positive"]
                ):
                    issue(
                        "NORMALIZATION_DIFFERENT",
                        "标准化参考区间或指标方向不同，不能直接计算分差。",
                    )
            difference("weights", a["weights"], b["weights"])
            if a["weights"] != b["weights"]:
                report["mode"] = "method_sensitivity"
                report["basis"] = (
                    "同一资料、方法和标准化基准下的权重敏感性；分差不表示时间变化或优劣决策。"
                )
            if len(a["row_ids"]) != len(a["scores"]) or len(b["row_ids"]) != len(b["scores"]):
                raise ValueError("score identity count")
            rows_a = [
                {"id": i, "score": number(v)}
                for i, v in zip(a["row_ids"], a["scores"], strict=True)
            ]
            rows_b = [
                {"id": i, "score": number(v)}
                for i, v in zip(b["row_ids"], b["scores"], strict=True)
            ]
            for ra, rb in aligned(rows_a, rows_b, "id"):
                report["rows"].append(
                    {
                        "id": ra["id"],
                        "left": ra["score"],
                        "right": rb["score"],
                        "difference": rb["score"] - ra["score"],
                        "unit": "1",
                    }
                )
        elif left_kind == "temporal":
            for key in [
                "variable",
                "method",
                "calendar",
                "start",
                "end",
                "target",
                "scope",
                "adaptation",
                "source_observation_indices",
                "source_times",
                "time_axis_unit",
                "cell_methods",
                "standard_version",
            ]:
                difference(key, a.get(key), b.get(key))
                if a.get(key) != b.get(key):
                    issue(
                        "TEMPORAL_SUPPORT_DIFFERENT",
                        "时间变量、日历、区间或适配依据不同，不能直接比较。",
                    )
            target_unit = a["conversion"]["target_unit"]
            converted = conversion(b["value"], b["conversion"]["target_unit"], target_unit)
            if converted is not None:
                report["rows"] = [
                    {
                        "id": a["variable"],
                        "left": number(a["value"]),
                        "right": converted,
                        "difference": converted - a["value"],
                        "unit": target_unit,
                    }
                ]
                delta = UNITS.Quantity(converted, target_unit) - UNITS.Quantity(
                    a["value"], target_unit
                )
                number(float(delta.magnitude))
                if delta.units != UNITS.Unit(target_unit):
                    report["rows"][0]["difference_unit"] = str(delta.units)
        elif left_kind == "optimization":
            ca = left["manifest"]["method"]["spec"]["configuration"]
            cb = right["manifest"]["method"]["spec"]["configuration"]
            constraints = {"budget", "minimum_area", "maximum_ecological_cost", "maximum_risk"}
            for key in sorted(set(ca) | set(cb)):
                difference(key, ca.get(key), cb.get(key))
                if key not in constraints | {"time_limit"} and ca.get(key) != cb.get(key):
                    issue("METHOD_DIFFERENT", "优化目标、量纲或风险可加性依据不同，不能直接比较。")
            report["mode"] = "constraint_sensitivity"
            report["basis"] = "同一候选单元与科学解释下的约束敏感性；选择变化不代表政策批准。"
            if not a.get("constraints_satisfied") or not b.get("constraints_satisfied"):
                issue("INFEASIBLE_RESULT", "至少一项成果未满足约束；未知选择不能当作未选或零收益。")
            for ra, rb in aligned(a["allocations"], b["allocations"], "id"):
                if any(
                    ra[k] != rb[k]
                    for k in ["allowed", "benefit", "cost", "area", "ecological_cost", "risk"]
                ):
                    issue("CANDIDATE_DIFFERENT", "候选单元数值或保护条件不同，需先核对科学依据。")
                if type(ra["selected"]) is not bool or type(rb["selected"]) is not bool:
                    issue("INFEASIBLE_RESULT", "选中状态未知，不生成数值差异。")
                else:
                    report["rows"].append(
                        {
                            "id": ra["id"],
                            "left": ra["selected"],
                            "right": rb["selected"],
                            "difference": int(rb["selected"]) - int(ra["selected"]),
                            "unit": "selection",
                        }
                    )
        else:
            issue("COMPARISON_NOT_READY", "此类成果尚未接入数值可比性规则；可分别查看原始成果。")
    except (KeyError, TypeError, ValueError):
        issue("RESULT_CONTRACT_INVALID", "成果缺少完整数值、标识或科学依据，不能比较。")
    report["issues"] = list({i["code"]: i for i in report["issues"]}.values())
    report["comparable"] = not report["issues"]
    if report["issues"]:
        report["rows"] = []
    return report
