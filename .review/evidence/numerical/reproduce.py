"""Run: next/.venv/bin/python .review/evidence/numerical/reproduce.py.

Small deterministic engineering cases, not validation against real business observations.
Writes JSON to stdout so reviewers may compare without overwriting recorded evidence.
"""
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'next/src'), str(ROOT / 'next/vendor')]
import numpy as np
from coastmas_next.indicator_kernels_v1 import spectral
from coastmas_next.planning_solver_v1 import solve, check_candidate

bands = {'red': np.array([0.2, 0, 0.2]), 'nir': np.array([0.6, 0, 0.6])}
masks = {k: np.array([True, True, False]) for k in bands}
values, valid = spectral('indicator.ndvi', bands, masks, {})
assert abs(values[0] - 0.5) <= 1e-12
assert valid.tolist() == [True, False, False]

problem = {
    'unit_ids': ['a', 'b', 'c'], 'mode': 'pareto_multiobjective',
    'objectives': [
        {'code': 'cost', 'direction': 'min', 'coefficients': [2., 5., 3.], 'unit': 'CNY'},
        {'code': 'gain', 'direction': 'max', 'coefficients': [4., 8., 5.], 'unit': 'ha'},
    ],
    'constraints': [{'id': 'budget', 'coefficients': [2., 5., 3.], 'upper': 5., 'unit': 'CNY'}],
    'upper_bounds': [1, 1, 1],
}
pareto = solve(problem, threading.Event())
assert {tuple(c['selected']) for c in pareto['candidates']} == {(), ('a',), ('c',), ('a', 'c')}
assert pareto['searched_states'] == pareto['total_states'] == 8
single = {**problem, 'mode': 'single_objective', 'objectives': [problem['objectives'][1]]}
milp = solve(single, threading.Event())
assert milp['candidates'][0]['selected'] == ['a', 'c']
assert milp['candidates'][0]['objective_vector'] == {'gain': 9.0}
infeasible = check_candidate(single, [1, 1, 1])
assert infeasible['feasible'] is False
print(json.dumps({
    'origin_kind': 'engineering_fixture', 'status': 'PASS', 'absolute_tolerance': 1e-12,
    'ndvi': {'bands': {k: v.tolist() for k, v in bands.items()},
             'masks': {k: v.tolist() for k, v in masks.items()},
             'values': [float(v) if ok else None for v, ok in zip(values, valid)],
             'valid': valid.tolist(), 'algorithm': 'spectral/1.0.0'},
    'planning_problem': problem, 'pareto': pareto, 'milp': milp,
    'independent_invalid_candidate_check': infeasible,
    'limitations': ['Small exact binary problem; no full Planning business acceptance.',
                    'No confidence, uncertainty, or business accuracy claim.'],
}, ensure_ascii=False, indent=2, allow_nan=False))
