"""Generate frontend schema/OpenAPI from Python contracts; --check never rewrites files."""

import argparse
import json
from pathlib import Path

from pydantic.json_schema import models_json_schema
from sqlalchemy import create_engine

from coastmas.app.api import create_app
from coastmas.app.indicator_routes import FrameworkPlanRequest, PrepareIndicatorsRequest
from coastmas.core.contracts import (
    BindingPlan,
    DataAssetSpec,
    ExecutionJob,
    ModelSpec,
    ResultManifest,
    RunManifest,
    SceneSpec,
    WorkflowSpec,
)
from coastmas.core.data_inspection import DataInspection
from coastmas.core.decomposition import DecompositionRequest, ModelDecomposition
from coastmas.core.geography import GeographicEntity
from coastmas.core.indicators import AssessmentSpec, IndicatorFrameworkSpec
from coastmas.core.knowledge_graph import GraphSnapshot
from coastmas.core.llm import ProviderPlanningArtifact, ProviderProposal
from coastmas.core.planning import ManagementGoal, PlanningArtifact
from coastmas.core.result_entities import ResultView
from coastmas.core.scene_workspace import SceneInspection
from coastmas.core.source_catalog import DataSourceSpec, SourceSnapshotRequest

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    contracts = [
        IndicatorFrameworkSpec,
        AssessmentSpec,
        PrepareIndicatorsRequest,
        FrameworkPlanRequest,
        DataSourceSpec,
        SourceSnapshotRequest,
        DataInspection,
        DecompositionRequest,
        ModelDecomposition,
        ResultView,
        SceneInspection,
        GraphSnapshot,
        GeographicEntity,
        ModelSpec,
        DataAssetSpec,
        SceneSpec,
        WorkflowSpec,
        BindingPlan,
        ExecutionJob,
        RunManifest,
        ResultManifest,
        ManagementGoal,
        PlanningArtifact,
        ProviderProposal,
        ProviderPlanningArtifact,
    ]
    references, schema = models_json_schema(
        [(model, "validation") for model in contracts], title="CoastMASContracts"
    )
    schema.update(
        type="object",
        additionalProperties=False,
        properties={model.__name__: references[(model, "validation")] for model in contracts},
        required=[model.__name__ for model in contracts],
    )
    # Creating an Engine is lazy; schema export does not connect to a database.
    engine = create_engine("postgresql+psycopg://coastmas@127.0.0.1/coastmas")
    app = create_app(engine)
    outputs = {
        ROOT / "apps/web/contracts.schema.json": schema,
        ROOT / "docs/openapi.json": app.openapi(),
    }
    for path, value in outputs.items():
        content = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if args.check:
            if not path.is_file() or path.read_text() != content:
                raise SystemExit("Generated schema is stale: " + str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    engine.dispose()


if __name__ == "__main__":
    main()
