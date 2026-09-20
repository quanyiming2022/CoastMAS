from datetime import UTC, datetime
from pathlib import Path

from coastmas.adapters.datasource import StoredDataResolver
from coastmas.adapters.geofiles import decode_geotiff
from coastmas.core.contracts import DataAssetSpec, RunManifest, WorkflowSpec
from coastmas.core.data_inspection import inspect_data
from coastmas.core.execution import execute_workflow
from coastmas.core.planning import build_template_plan, parse_template_goal
from coastmas.domain.coastal_catalog import coastal_catalog, coastal_sample_scene


def test_scenario_a_registered_dag_reads_actual_tiff_geojson_csv(storage, tmp_path):
    directory = Path("sample-data")
    catalog = coastal_catalog("coastal-test", directory)
    models = {item.runtime_config["component"]: item for item in catalog.models}
    scene = coastal_sample_scene(directory)
    configurations = [
        ("dem", "dem.tif", "raster", "GeoTIFF", "screening"),
        ("land_cover", "land_cover_t1.tif", "raster", "GeoTIFF", "overlay"),
        ("units", "management_units.geojson", "vector", "GeoJSON", "overlay"),
        ("population", "population.csv", "table", "CSV", "overlay"),
    ]
    assets = []
    bindings = []
    for name, filename, kind, format, target_node in configurations:
        content = (directory / filename).read_bytes()
        artifact = storage.put("coastal/" + filename, content)
        variable = next(item for item in models[target_node].inputs if item.name == name)
        crs, datum = None, None
        if kind == "raster":
            grid = decode_geotiff(content)
            crs, datum = grid.crs, grid.vertical_datum
            variable = variable.model_copy(update={"unit": grid.unit})
        elif kind == "vector":
            crs = "EPSG:4326"
        source = DataAssetSpec(
            id=name,
            name=name,
            type=kind,
            format=format,
            uri=artifact.uri,
            checksum=artifact.sha256,
            crs=crs,
            vertical_datum=datum,
            spatial_extent=None,
            time_start=scene.time_range.start,
            time_end=scene.time_range.end,
            time_resolution="1 day",
            variables=(variable,),
            quality={"column_units": {"population": "person"}} if name == "population" else {},
            source="SYNTHETIC / DEMONSTRATION DATA",
            license="CC0",
            version=1,
        )
        report = inspect_data(content, source)
        source = source.model_copy(update={"quality": {**source.quality, **report.metadata}})
        assets.append(source)
        bindings.append(
            {
                "source": {"id": name, "version": 1},
                "target": {"node_id": target_node, "variable": name},
                "semantic_mapping": "exact_standard_name",
                "unit_conversion": None,
                "crs_transform": None,
                "resampling": None,
                "temporal_transform": None,
                "quality_check": [],
                "status": "MANUAL_REVIEW",
            }
        )
    graph = WorkflowSpec.model_validate(
        {
            "id": "coastal",
            "name": "coastal",
            "version": 1,
            "scene_type": "A",
            "nodes": [
                {
                    "id": name,
                    "model_id": models[name].id,
                    "model_version": 1,
                    "parameters": {"increment": 0.5} if name == "screening" else {},
                }
                for name in ("screening", "overlay", "statistics")
            ],
            "edges": [
                {
                    "source_node": "screening",
                    "source_variable": "inundation",
                    "target_node": "overlay",
                    "target_variable": "inundation",
                },
                {
                    "source_node": "overlay",
                    "source_variable": "impacts",
                    "target_node": "statistics",
                    "target_variable": "impacts",
                },
            ],
            "input_bindings": bindings,
            "parameter_bindings": [],
            "constraints": [],
            "validation_rules": [],
            "execution_policy": {"timeout_seconds": 30, "max_retries": 0},
            "output_definition": [
                {"node_id": "statistics", "variable": "statistics"},
                {"node_id": "screening", "variable": "polygons"},
            ],
        }
    )
    plan = build_template_plan(
        parse_template_goal("海岸影响筛查：海平面上升0.5米"),
        scene,
        catalog.models,
        tuple(assets),
        catalog.registry,
    )
    assert not plan.missing_conditions, plan.missing_conditions
    assert plan.candidate_workflow is not None
    assert plan.candidate_workflow.edges == graph.edges
    graph = plan.candidate_workflow
    selected = {node.model_id for node in graph.nodes}
    run = RunManifest(
        scene=scene,
        workflow=graph,
        models=tuple(item for item in catalog.models if item.id in selected),
        data_assets=tuple(assets),
        parameters=(),
        bindings=graph.input_bindings,
        random_seed=42,
        software_version="test",
        container_image="local-test",
        timestamp=datetime.now(UTC),
        environment={},
    )
    result = execute_workflow(
        run, registry=catalog.registry, resolver=StoredDataResolver(storage), work_root=tmp_path
    )
    assert result.executed_nodes == ("screening", "overlay", "statistics")
    assert result.outputs["statistics.statistics"]["estimated_affected_population"] == 320
    assert result.outputs["statistics.statistics"]["inundated_area_m2"] == 80000
    assert result.outputs["screening.polygons"]["features"]
