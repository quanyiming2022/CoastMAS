"""Independent ratio-matrix and bad-science cases for evaluation weights."""

import io

import numpy as np
import pytest


def test_ratio_matrix_identity_order_and_inconsistent_rejection():
    from coastmas_next.ahp import derive_weights

    # Ratios constructed from an independently specified weight vector, not solver output.
    matrix = [[1.0, 2 / 3, 2 / 5], [3 / 2, 1.0, 3 / 5], [5 / 2, 5 / 3, 1.0]]
    outcome = derive_weights(["a", "b", "c"], matrix, ["c", "a", "b"], 0.1)
    assert np.allclose(outcome["weights"], [0.5, 0.2, 0.3], atol=1e-12)
    assert outcome["consistency_ratio"] < 1e-12
    assert outcome["algorithm"] == "principal_eigenvector"
    assert outcome["consistency_applicable"] is True
    assert matrix[0][1] == 2 / 3
    from coastmas_next.store import Problem

    for labels, bad in [
        (["a", "a", "c"], matrix),
        (["a", "b", "c"], [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]]),
        (["a", "b", "c"], [[1, 2, None], [0.5, 1, 3], [0.25, 1 / 3, 1]]),
    ]:
        with pytest.raises(Problem):
            derive_weights(labels, bad, ["a", "b", "c"], 0.1)
    with pytest.raises(Problem) as invalid:
        derive_weights(["a", "b"], [[1, 2], [0.3, 1]], ["a", "b"], 0.1)
    assert invalid.value.code == "AHP_RECIPROCAL"
    small = derive_weights(["a", "b"], [[1, 2], [0.5, 1]], ["a", "b"], 0.1)
    assert small["consistency_ratio"] is None and small["consistency_applicable"] is False


def test_matrix_csv_xlsx_mapping_and_formula_rejection(workspace):
    _, _, client, project = workspace
    raw = "指标,b,a\nb,1,2\na,0.5,1\n".encode()
    response = client.post(
        f"/api/projects/{project}/ahp/import",
        files={"file": ("matrix.csv", raw)},
        data={"indicators": '["a","b"]', "consistency_limit": "0.1"},
    )
    assert response.status_code == 200, response.text
    assert np.allclose(response.json()["report"]["weights"], [1 / 3, 2 / 3])
    assert response.json()["definition"]["labels"] == ["b", "a"]
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(["指标", "a", "b"])
    sheet.append(["a", 1, "=2"])
    sheet.append(["b", 0.5, 1])
    data = io.BytesIO()
    book.save(data)
    invalid = client.post(
        f"/api/projects/{project}/ahp/import",
        files={"file": ("matrix.xlsx", data.getvalue())},
        data={"indicators": '["a","b"]', "consistency_limit": "0.1"},
    )
    assert invalid.status_code == 422


def test_published_ahp_actually_computes_point66_and_contributions(workspace):
    from test_decisions import prepare

    from coastmas_next.worker import Worker

    _, store, client, project = workspace
    config = {
        "task": "assessment",
        "method": "weighted",
        "indicators": [
            {
                "concept": key,
                "unit": "1",
                "lower": 0.0,
                "upper": 1.0,
                "positive": True,
                "weight": None,
            }
            for key in ["a", "b", "c"]
        ],
        "weighting": {
            "method": "ahp",
            "labels": ["a", "b", "c"],
            "matrix": [[1.0, 2 / 3, 2 / 5], [3 / 2, 1.0, 3 / 5], [5 / 2, 5 / 3, 1.0]],
            "consistency_limit": 0.1,
        },
    }
    task = prepare(
        client,
        project,
        "assessment",
        b"id,a,b,c\n01,.4,.6,.8\n02,.4,.6,.8\n",
        {
            key: {"role": "feature", "concept": key, "unit": "1", "support": "point"}
            for key in ["a", "b", "c"]
        },
        config,
    )
    response = client.post(
        f"/api/tasks/{task['id']}/execute",
        json={"expected_revision": task["revision"], "idempotency_key": "ahp-real"},
    )
    assert response.status_code == 202, response.text
    assert Worker(store).run_once()
    result = client.get(f"/api/jobs/{response.json()['id']}/result").json()
    assert np.allclose(result["data"]["scores"], [0.66, 0.66], atol=1e-12)
    assert np.allclose(result["data"]["contributions"][0], [0.08, 0.18, 0.40], atol=1e-12)
    assert result["data"]["weight_evidence"]["consistency_ratio"] < 1e-12
    assert result["states"]["business_validated"] is False
