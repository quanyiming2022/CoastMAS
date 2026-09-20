"""Bounded graph projection of versioned contracts, never an execution approval."""

import hashlib
import json
from typing import Annotated, Literal, Self

import networkx as nx  # type: ignore[import-untyped]
from pydantic import Field, JsonValue, model_validator

from coastmas.core.contracts import (
    Contract,
    DataAssetSpec,
    ModelSpec,
    Name,
    SceneSpec,
    VariableSpec,
    VersionReference,
    WorkflowSpec,
)

NodeType = Literal[
    "Objective",
    "Task",
    "Model",
    "Variable",
    "DataType",
    "EntityType",
    "SceneType",
    "Constraint",
    "DataAsset",
    "Scene",
    "Workflow",
]
Relation = Literal[
    "REQUIRES",
    "PRODUCES",
    "SUPPORTS",
    "DEPENDS_ON",
    "MAPS_TO",
    "VALID_FOR",
    "INCOMPATIBLE_WITH",
    "DERIVED_FROM",
    "CAN_FOLLOW",
]


class GraphNode(Contract):
    id: Name
    type: NodeType
    label: Name
    resource: VersionReference | None = None
    properties: dict[str, JsonValue] = Field(default_factory=dict)


class GraphEdge(Contract):
    id: Name
    source: Name
    target: Name
    type: Relation
    evidence: Literal[
        "declaration", "workflow_declaration", "contract_candidate", "contract_conflict"
    ]
    properties: dict[str, JsonValue] = Field(default_factory=dict)


class GraphSnapshot(Contract):
    nodes: Annotated[tuple[GraphNode, ...], Field(max_length=10000)]
    edges: Annotated[tuple[GraphEdge, ...], Field(max_length=50000)]

    @model_validator(mode="after")
    def referential_integrity(self) -> Self:
        identities = {node.id for node in self.nodes}
        if len(identities) != len(self.nodes) or len({edge.id for edge in self.edges}) != len(
            self.edges
        ):
            raise ValueError("duplicate graph identity")
        if any(
            edge.source not in identities or edge.target not in identities for edge in self.edges
        ):
            raise ValueError("dangling graph relationship")
        return self


def graph_id(kind: str, payload: JsonValue) -> str:
    value = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return kind + ":" + hashlib.sha256(value.encode()).hexdigest()[:32]


class KnowledgeGraphService:
    """PostgreSQL contracts are the source of truth; NetworkX serves local traversal."""

    def __init__(self, snapshot: GraphSnapshot):
        self.snapshot = snapshot
        self.graph = nx.MultiDiGraph()
        self.graph.add_nodes_from(node.id for node in snapshot.nodes)
        self.graph.add_edges_from((edge.source, edge.target, edge.id) for edge in snapshot.edges)

    def neighborhood(self, identifier: str, depth: int = 2) -> GraphSnapshot:
        if identifier not in self.graph:
            raise ValueError("graph node unavailable")
        if not 0 <= depth <= 4:
            raise ValueError("graph depth must be between zero and four")
        selected = set(
            nx.single_source_shortest_path_length(
                self.graph.to_undirected(), identifier, cutoff=depth
            )
        )
        return GraphSnapshot(
            nodes=tuple(node for node in self.snapshot.nodes if node.id in selected),
            edges=tuple(
                edge
                for edge in self.snapshot.edges
                if edge.source in selected and edge.target in selected
            ),
        )

    @classmethod
    def from_catalog(
        cls,
        *,
        models: tuple[ModelSpec, ...] = (),
        assets: tuple[DataAssetSpec, ...] = (),
        scenes: tuple[SceneSpec, ...] = (),
        workflows: tuple[WorkflowSpec, ...] = (),
    ) -> Self:
        if len(models) + len(assets) + len(scenes) + len(workflows) > 500:
            raise ValueError("graph catalog exceeds 500 resource versions")
        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}
        variables: dict[str, VariableSpec] = {}
        model_inputs: dict[str, list[str]] = {}
        model_outputs: dict[str, list[str]] = {}

        def node(
            kind: NodeType,
            label: str,
            identity: JsonValue,
            resource: VersionReference | None = None,
            properties: dict[str, JsonValue] | None = None,
        ) -> str:
            identifier = graph_id(kind, identity)
            nodes[identifier] = GraphNode(
                id=identifier,
                type=kind,
                label=label,
                resource=resource,
                properties=properties or {},
            )
            if len(nodes) > 10000:
                raise ValueError("graph node budget exceeded")
            return identifier

        def edge(
            source: str,
            target: str,
            kind: Relation,
            evidence: Literal[
                "declaration", "workflow_declaration", "contract_candidate", "contract_conflict"
            ] = "declaration",
            properties: dict[str, JsonValue] | None = None,
        ) -> None:
            payload = properties or {}
            identifier = graph_id(kind, [source, target, evidence, payload])
            edges[identifier] = GraphEdge(
                id=identifier,
                source=source,
                target=target,
                type=kind,
                evidence=evidence,
                properties=payload,
            )
            if len(edges) > 50000:
                raise ValueError("graph edge budget exceeded")

        def resource_node(kind: NodeType, identifier: str, version: int, label: str) -> str:
            reference = VersionReference(id=identifier, version=version)
            key = graph_id(kind, reference.model_dump(mode="json"))
            if key in nodes:
                return key
            return node(kind, label, reference.model_dump(mode="json"), reference)

        def variable_node(variable: VariableSpec) -> str:
            # Port names/descriptions are contextual; all scientific semantics remain in identity.
            properties = variable.model_dump(
                mode="json", exclude={"name", "description", "required"}
            )
            identifier = node("Variable", variable.standard_name, properties, properties=properties)
            variables[identifier] = variable
            dtype = node("DataType", variable.data_type, variable.data_type)
            edge(identifier, dtype, "MAPS_TO")
            return identifier

        for model in sorted(models, key=lambda item: (item.id, item.version)):
            identifier = resource_node("Model", model.id, model.version, model.display_name)
            model_inputs[identifier], model_outputs[identifier] = [], []
            for variable in model.inputs:
                target = variable_node(variable)
                model_inputs[identifier].append(target)
                edge(
                    identifier,
                    target,
                    "REQUIRES",
                    properties={"port": variable.name, "required": variable.required},
                )
            for variable in model.outputs:
                target = variable_node(variable)
                model_outputs[identifier].append(target)
                edge(identifier, target, "PRODUCES", properties={"port": variable.name})
            for capability in model.capabilities:
                edge(identifier, node("Task", capability, capability), "SUPPORTS")
            for constraint in model.constraints:
                payload = constraint.model_dump(mode="json")
                edge(
                    identifier,
                    node(
                        "Constraint",
                        constraint.description or constraint.field,
                        payload,
                        properties=payload,
                    ),
                    "REQUIRES",
                )

        for asset in sorted(assets, key=lambda item: (item.id, item.version)):
            identifier = resource_node("DataAsset", asset.id, asset.version, asset.name)
            for variable in asset.variables:
                edge(
                    identifier,
                    variable_node(variable),
                    "PRODUCES",
                    properties={"port": variable.name},
                )

        for scene in sorted(scenes, key=lambda item: (item.id, item.version)):
            identifier = resource_node("Scene", scene.id, scene.version, scene.name)
            edge(
                identifier,
                node("Objective", scene.management_goal, scene.management_goal),
                "REQUIRES",
            )
            for kind in scene.entity_types:
                edge(identifier, node("EntityType", kind, kind), "VALID_FOR")
            for constraint in scene.constraints:
                payload = constraint.model_dump(mode="json")
                edge(
                    identifier,
                    node(
                        "Constraint",
                        constraint.description or constraint.field,
                        payload,
                        properties=payload,
                    ),
                    "REQUIRES",
                )

        # Exact metadata compatibility is a candidate link, not scientific preflight success.
        for source, outputs in sorted(model_outputs.items()):
            for target, inputs in sorted(model_inputs.items()):
                common = sorted(set(outputs) & set(inputs))
                if source != target and common:
                    edge(
                        source,
                        target,
                        "CAN_FOLLOW",
                        "contract_candidate",
                        {
                            "shared_variables": [value for value in common],
                            "requires_preflight": True,
                        },
                    )
        by_standard: dict[str, list[str]] = {}
        for identifier, variable in variables.items():
            by_standard.setdefault(variable.standard_name, []).append(identifier)
        if sum(len(group) * (len(group) - 1) // 2 for group in by_standard.values()) > 250000:
            raise ValueError("graph semantic comparison budget exceeded")
        for group in by_standard.values():
            for index, source in enumerate(sorted(group)):
                for target in sorted(group)[index + 1 :]:
                    left, right = variables[source], variables[target]
                    if (
                        left.dimension != right.dimension
                        or left.semantic_type != right.semantic_type
                    ):
                        edge(
                            source,
                            target,
                            "INCOMPATIBLE_WITH",
                            "contract_conflict",
                            {"reason": "declared dimension or semantic type differs"},
                        )

        for workflow in sorted(workflows, key=lambda item: (item.id, item.version)):
            identifier = resource_node("Workflow", workflow.id, workflow.version, workflow.name)
            edge(
                identifier, node("SceneType", workflow.scene_type, workflow.scene_type), "VALID_FOR"
            )
            tasks: dict[str, str] = {}
            for step in workflow.nodes:
                tasks[step.id] = node(
                    "Task",
                    step.id,
                    [workflow.id, workflow.version, step.id],
                    properties={
                        "parameters": {key: value for key, value in step.parameters.items()}
                    },
                )
                edge(identifier, tasks[step.id], "REQUIRES", "workflow_declaration")
                model_id = resource_node("Model", step.model_id, step.model_version, step.model_id)
                edge(tasks[step.id], model_id, "DERIVED_FROM", "workflow_declaration")
            for connection in workflow.edges:
                edge(
                    tasks[connection.target_node],
                    tasks[connection.source_node],
                    "DEPENDS_ON",
                    "workflow_declaration",
                    {
                        "source_port": connection.source_variable,
                        "target_port": connection.target_variable,
                    },
                )
            for binding in workflow.input_bindings:
                source = resource_node(
                    "DataAsset", binding.source.id, binding.source.version, binding.source.id
                )
                edge(
                    source,
                    tasks[binding.target.node_id],
                    "MAPS_TO",
                    "workflow_declaration",
                    {
                        "target_port": binding.target.variable,
                        "binding": binding.model_dump(mode="json"),
                    },
                )
        return cls(
            GraphSnapshot(
                nodes=tuple(nodes[key] for key in sorted(nodes)),
                edges=tuple(edges[key] for key in sorted(edges)),
            )
        )
