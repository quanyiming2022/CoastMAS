import pytest
from pydantic import ValidationError

from coastmas.core.knowledge_graph import GraphEdge, GraphNode, GraphSnapshot, KnowledgeGraphService
from tests.factories import asset, model, scene, variable


def test_graph_follows_real_model_input_data_and_downstream_contracts():
    upstream = model(id="upstream", outputs=[variable(name="produced")])
    downstream = model(id="downstream")
    graph = KnowledgeGraphService.from_catalog(
        models=(upstream, downstream), assets=(asset(),), scenes=(scene(),)
    )
    model_nodes = [node for node in graph.snapshot.nodes if node.type == "Model"]
    assert len(model_nodes) == 2
    assert {"Model", "Variable", "DataType", "DataAsset", "Objective", "EntityType", "Scene"} <= {
        node.type for node in graph.snapshot.nodes
    }
    edges = graph.snapshot.edges
    assert {"REQUIRES", "PRODUCES", "SUPPORTS", "VALID_FOR", "CAN_FOLLOW"} <= {
        edge.type for edge in edges
    }
    follows = [edge for edge in edges if edge.type == "CAN_FOLLOW"]
    assert all(edge.evidence == "contract_candidate" for edge in follows)
    center = next(node.id for node in model_nodes if node.resource.id == "downstream")
    neighborhood = graph.neighborhood(center, depth=2)
    assert any(node.type == "DataAsset" for node in neighborhood.nodes)
    assert all(
        edge.source in {node.id for node in neighborhood.nodes}
        and edge.target in {node.id for node in neighborhood.nodes}
        for edge in neighborhood.edges
    )


def test_graph_is_stable_across_catalog_order_and_does_not_expose_runtime_secrets():
    a = model(id="a", runtime_config={"authorization": "private-value"})
    b = model(id="b")
    first = KnowledgeGraphService.from_catalog(models=(a, b)).snapshot
    second = KnowledgeGraphService.from_catalog(models=(b, a)).snapshot
    assert first == second
    assert "private-value" not in first.model_dump_json()
    with pytest.raises(ValueError, match="node"):
        KnowledgeGraphService(first).neighborhood("missing")


def test_graph_rejects_dangling_or_duplicate_identities_and_unsupported_relations():
    node = GraphNode(id="a", type="Model", label="A")
    with pytest.raises(ValidationError):
        GraphSnapshot(nodes=(node, node), edges=())
    with pytest.raises(ValidationError):
        GraphSnapshot(
            nodes=(node,),
            edges=(
                GraphEdge(
                    id="e", source="a", target="missing", type="REQUIRES", evidence="declaration"
                ),
            ),
        )
    with pytest.raises(ValidationError):
        GraphEdge(id="e", source="a", target="a", type="GUESSED", evidence="declaration")


def test_workflow_relations_constraints_and_conflicts_have_declared_evidence():
    from tests.factories import workflow

    constraint = {
        "field": "crs",
        "operator": "required",
        "value": True,
        "description": "Explicit CRS required",
    }
    first = model(constraints=[constraint])
    second = model(id="next", inputs=[variable(unit="s", dimension="[time]")])
    composed = workflow(
        nodes=[
            {"id": "screen-node", "model_id": "screen", "model_version": 1},
            {"id": "next-node", "model_id": "next", "model_version": 1},
        ],
        edges=[
            {
                "source_node": "screen-node",
                "source_variable": "result",
                "target_node": "next-node",
                "target_variable": "height",
            }
        ],
    )
    graph = KnowledgeGraphService.from_catalog(
        models=(first, second),
        assets=(asset(),),
        scenes=(scene(constraints=[constraint]),),
        workflows=(composed,),
    )
    relations = {edge.type for edge in graph.snapshot.edges}
    assert {
        "REQUIRES",
        "PRODUCES",
        "SUPPORTS",
        "DEPENDS_ON",
        "MAPS_TO",
        "VALID_FOR",
        "INCOMPATIBLE_WITH",
        "DERIVED_FROM",
        "CAN_FOLLOW",
    } <= relations
    assert {"SceneType", "Constraint", "Workflow"} <= {node.type for node in graph.snapshot.nodes}
    assert all(
        edge.evidence == "contract_conflict"
        for edge in graph.snapshot.edges
        if edge.type == "INCOMPATIBLE_WITH"
    )
    assert all(
        edge.evidence == "workflow_declaration"
        for edge in graph.snapshot.edges
        if edge.type in {"DEPENDS_ON", "DERIVED_FROM"}
    )
    center = graph.snapshot.nodes[0].id
    assert len(graph.neighborhood(center, 0).nodes) == 1
    with pytest.raises(ValueError, match="depth"):
        graph.neighborhood(center, 5)
    with pytest.raises(ValueError, match="500"):
        KnowledgeGraphService.from_catalog(models=(first,) * 501)
