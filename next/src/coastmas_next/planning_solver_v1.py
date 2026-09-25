"""Binary planning kernels. Keep released bytes immutable; register a new version to change them.

The exact Pareto solver is bounded to small complete problems. It never samples
units or chooses a preferred plan. Larger problems need a different matched solver.
This worker kernel accepts already compiled numeric units, not user code or policy.
"""

import math
import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from .store import Problem

VERSION = "1.0.0"
ABS_TOLERANCE = 1e-7
PARETO_MAX_UNITS = 18
MAX_FRONT = 10000


def fail(code, message):
    raise Problem(422, code, message)


def finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def validate(problem):
    ids = problem.get("unit_ids", [])
    if not ids or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        fail("PLANNING_UNIT_IDENTITY", "规划单元标识必须存在且唯一")
    mode, objectives = problem.get("mode"), problem.get("objectives", [])
    if mode not in {"single_objective", "weighted_multiobjective", "pareto_multiobjective"}:
        fail("OBJECTIVE_MODE", "规划目标模式无效")
    if not objectives or (mode == "single_objective" and len(objectives) != 1):
        fail("OBJECTIVE_COUNT", "目标数量与模式不匹配")
    if mode != "single_objective" and len(objectives) < 2:
        fail("OBJECTIVE_COUNT", "多目标至少需要两项")
    if len({x.get("code") for x in objectives}) != len(objectives):
        fail("OBJECTIVE_DUPLICATE", "目标标识重复")
    for objective in objectives:
        if not objective.get("code") or objective.get("direction") not in {"min", "max"}:
            fail("OBJECTIVE_DIRECTION", "必须固定真实目标和优化方向")
        if not isinstance(objective.get("unit"), str) or not objective["unit"].strip():
            fail("OBJECTIVE_UNIT_UNKNOWN", "目标单位尚未确认")
    rows = problem.get("constraints", [])
    if len({x.get("id") for x in rows}) != len(rows):
        fail("CONSTRAINT_IDENTITY", "约束标识重复")
    for item in [*objectives, *rows]:
        column = item.get("coefficients", [])
        if len(column) != len(ids) or any(not finite(x) for x in column):
            fail("PLANNING_COEFFICIENT_UNKNOWN", "逐单元数值缺失或索引不一致，不自动补零")
    for row in rows:
        if not row.get("id") or not row.get("unit"):
            fail("CONSTRAINT_DEFINITION", "约束标识和单位必须明确")
        if not any(k in row for k in ("lower", "upper")):
            fail("CONSTRAINT_BOUND_REQUIRED", "约束没有明确边界")
        if any(k in row and not finite(row[k]) for k in ("lower", "upper")):
            fail("CONSTRAINT_BOUND_UNKNOWN", "约束上限或下限未知")
        if row.get("lower", -math.inf) > row.get("upper", math.inf):
            fail("CONSTRAINT_BOUND_ORDER", "约束下限不能大于上限")
    allowed = problem.get("upper_bounds", [])
    if len(allowed) != len(ids) or any(type(x) is not int or x not in {0, 1} for x in allowed):
        fail("DECISION_DOMAIN_UNKNOWN", "每个规划单元必须具有明确的允许改变状态")
    if mode == "weighted_multiobjective":
        for objective in objectives:
            scale = objective.get("scale", {})
            if not all(finite(scale.get(k)) for k in ("lower", "upper")) or not scale.get("basis"):
                fail("OBJECTIVE_SCALE_REQUIRED", "不同目标加权前需要有依据的价值转换范围")
            if scale["upper"] <= scale["lower"]:
                fail("OBJECTIVE_SCALE_INVALID", "价值转换范围必须递增")
            if not finite(objective.get("weight")) or not 0 <= objective["weight"] <= 1:
                fail("OBJECTIVE_WEIGHT_REQUIRED", "请明确目标权重，不自动设置")
        if not math.isclose(math.fsum(x["weight"] for x in objectives), 1.0, abs_tol=1e-9):
            fail("OBJECTIVE_WEIGHT_SUM", "目标权重之和必须为1")
    elif any("weight" in x for x in objectives):
        fail("OBJECTIVE_WEIGHT_SCOPE", "此模式不使用权重，不静默忽略已提供权重")
    return ids, objectives, rows, allowed


def check_candidate(problem, values):
    ids, _, rows, allowed = validate(problem)
    if len(values) != len(ids) or any(not finite(x) for x in values):
        fail("CANDIDATE_VALUES_INVALID", "候选方案没有完整有限的决策值")
    integral = all(abs(x - round(x)) <= ABS_TOLERANCE for x in values)
    binary = integral and all(
        0 <= round(x) <= upper for x, upper in zip(values, allowed, strict=True)
    )
    selected = [round(x) for x in values] if integral else values
    reports = []
    for row in rows:
        achieved = math.fsum(a * x for a, x in zip(row["coefficients"], selected, strict=True))
        lower = achieved - row["lower"] if "lower" in row else None
        upper = row["upper"] - achieved if "upper" in row else None
        feasible = (lower is None or lower >= -ABS_TOLERANCE) and (
            upper is None or upper >= -ABS_TOLERANCE
        )
        reports.append(
            {
                "id": row["id"],
                "achieved": achieved,
                "lower_residual": lower,
                "upper_residual": upper,
                "unit": row["unit"],
                "feasible": feasible,
            }
        )
    return {
        "feasible": binary and all(r["feasible"] for r in reports),
        "binary_domain": binary,
        "constraints": reports,
        "absolute_tolerance": ABS_TOLERANCE,
        "checker_version": VERSION,
    }


def candidate(problem, bits):
    report = check_candidate(problem, bits)
    if not report["feasible"]:
        return None
    values = {
        item["code"]: math.fsum(a * x for a, x in zip(item["coefficients"], bits, strict=True))
        for item in problem["objectives"]
    }
    return {
        "selected": [id for id, x in zip(problem["unit_ids"], bits, strict=True) if x],
        "decision_values": list(bits),
        "objective_vector": values,
        "feasibility": report,
        "business_state": "calculated",
        "business_validated": False,
    }


def canceled(event):
    if event.is_set():
        raise Problem(409, "CANCELLED", "规划求解已收到取消请求")


def dominates(a, b):
    # Both vectors have already been converted to minimization orientation.
    # Equal values preserve distinct spatial allocations; no artificial winner.
    return all(x <= y for x, y in zip(a, b, strict=True)) and any(
        x < y for x, y in zip(a, b, strict=True)
    )


def solve(problem, cancel, *, time_limit=60.0, progress=None):
    ids, objectives, rows, allowed = validate(problem)
    if not finite(time_limit) or not 0 < time_limit <= 120:
        fail("SOLVER_TIME_LIMIT", "求解时限必须在0到120秒之间")
    canceled(cancel)
    started = time.monotonic()
    if problem["mode"] == "pareto_multiobjective":
        if len(ids) > PARETO_MAX_UNITS:
            fail(
                "SOLVER_SCALE_RISK",
                "此精确多目标求解器最多支持18个完整单元；需匹配其他求解器，不会抽样替代",
            )
        front, total, processed = [], 2 ** len(ids), 0
        for state in range(total):
            canceled(cancel)
            if time.monotonic() - started >= time_limit:
                break
            bits = [(state >> i) & 1 for i in range(len(ids))]
            item = candidate(problem, bits)
            processed += 1
            if item:
                vector = [
                    item["objective_vector"][obj["code"]] * (1 if obj["direction"] == "min" else -1)
                    for obj in objectives
                ]
                if not any(dominates(v, vector) for v, _ in front):
                    front = [(v, c) for v, c in front if not dominates(vector, v)]
                    front.append((vector, item))
                    if len(front) > MAX_FRONT:
                        fail(
                            "PARETO_STORAGE_BUDGET",
                            "非支配候选超过此求解器预算，未截断或自动选择最佳方案",
                        )
            if progress and (processed % 128 == 0 or processed == total):
                progress({"processed": processed, "total": total, "stage": "pareto_search"})
        complete = processed == total
        return {
            "solver": "exact_binary_pareto/" + VERSION,
            "status": ("complete" if front else "infeasible") if complete else "partial_search",
            "searched_states": processed,
            "total_states": total,
            "pareto_scope": "complete_problem" if complete else "searched_states",
            "candidates": [c for _, c in front],
            "elapsed_seconds": time.monotonic() - started,
            "checkpoint_supported": False,
        }
    coefficients = np.zeros(len(ids))
    for objective in objectives:
        sign = 1 if objective["direction"] == "min" else -1
        factor = (
            objective["weight"] / (objective["scale"]["upper"] - objective["scale"]["lower"])
            if problem["mode"] == "weighted_multiobjective"
            else 1.0
        )
        coefficients += sign * factor * np.asarray(objective["coefficients"], dtype=float)
    constraints = (
        LinearConstraint(
            np.asarray([r["coefficients"] for r in rows], dtype=float),
            [r.get("lower", -np.inf) for r in rows],
            [r.get("upper", np.inf) for r in rows],
        )
        if rows
        else None
    )
    if progress:
        progress({"processed": None, "total": None, "stage": "milp"})
    solution = milp(
        coefficients,
        integrality=np.ones(len(ids)),
        bounds=Bounds(0, allowed),
        constraints=constraints,
        options={"time_limit": time_limit, "mip_rel_gap": 0.0},
    )
    canceled(cancel)
    status = int(solution.status)
    output = {
        "solver": "scipy_milp/" + VERSION,
        "candidates": [],
        "elapsed_seconds": time.monotonic() - started,
        "checkpoint_supported": False,
        "solver_message": str(solution.message),
    }
    if status == 2:
        return {**output, "status": "infeasible"}
    if solution.x is None or status not in {0, 1}:
        return {**output, "status": "time_limit" if status == 1 else "failed"}
    raw = [float(x) for x in solution.x]
    if not check_candidate(problem, raw)["feasible"]:
        fail("SOLVER_INVALID_CANDIDATE", "求解器返回的方案未通过独立可行性检查")
    return {
        **output,
        "status": "optimal" if status == 0 else "incumbent",
        "candidates": [candidate(problem, [round(x) for x in raw])],
    }
