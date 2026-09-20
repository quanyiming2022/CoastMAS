"""Static, reviewable model decomposition; source text is never imported or executed."""

import ast
from typing import Literal

from pydantic import Field

from coastmas.core.contracts import Contract, Name
from coastmas.core.errors import ConstraintError

Stage = Literal["preprocess", "compute", "postprocess", "validate"]


class ModelComponent(Contract):
    id: Name
    stage: Stage
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    atomic: bool = False
    signature: str | None = None
    description: str = ""


class DecompositionRequest(Contract):
    kind: Literal["python", "pipeline", "cli", "declared", "black_box"]
    name: Name
    source: str | None = Field(default=None, max_length=262144)
    argv: tuple[str, ...] = Field(default=(), max_length=1000)
    components: tuple[ModelComponent, ...] = Field(default=(), max_length=500)
    dependencies: tuple[tuple[str, str], ...] = Field(default=(), max_length=5000)


class ModelDecomposition(Contract):
    model_name: Name
    mode: Literal["WHITE_BOX", "BLACK_BOX"]
    components: tuple[ModelComponent, ...]
    dependencies: tuple[tuple[str, str], ...]
    cli_arguments: dict[str, str | bool] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    review_required: Literal[True] = True
    executable: Literal[False] = False


def validate_dependencies(
    components: tuple[ModelComponent, ...], edges: tuple[tuple[str, str], ...]
) -> None:
    identifiers = {component.id for component in components}
    if not identifiers or len(identifiers) != len(components):
        raise ConstraintError("components must be nonempty and uniquely identified")
    incoming = dict.fromkeys(identifiers, 0)
    adjacency: dict[str, list[str]] = {identifier: [] for identifier in identifiers}
    if len(set(edges)) != len(edges):
        raise ConstraintError("duplicate component dependency")
    for source, destination in edges:
        if source not in identifiers or destination not in identifiers:
            raise ConstraintError("component dependency references unknown component")
        incoming[destination] += 1
        adjacency[source].append(destination)
    ready = [identifier for identifier, count in incoming.items() if count == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for destination in adjacency[current]:
            incoming[destination] -= 1
            if incoming[destination] == 0:
                ready.append(destination)
    if visited != len(identifiers):
        raise ConstraintError("component dependency cycle requires explicit iterative modelling")


def python_components(
    source: str,
) -> tuple[tuple[ModelComponent, ...], tuple[tuple[str, str], ...], tuple[str, ...]]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, RecursionError) as exc:
        raise ConstraintError("model source is not valid bounded Python syntax") from exc
    if sum(1 for _ in ast.walk(tree)) > 20000:
        raise ConstraintError("model source AST exceeds inspection budget")
    functions: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    warnings: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append((node.name + "." + method.name, method))
            warnings.append(
                "class methods retain their class context and require registration review"
            )
        else:
            warnings.append("top-level statements are not executed")
    identifiers = {identifier for identifier, _ in functions}
    components = []
    dependencies: set[tuple[str, str]] = set()
    for identifier, function in functions:
        stage: Stage = "compute"
        for prefix in ("preprocess", "postprocess", "validate"):
            if function.name.startswith(prefix):
                if prefix == "preprocess":
                    stage = "preprocess"
                elif prefix == "postprocess":
                    stage = "postprocess"
                else:
                    stage = "validate"
                break
        arguments = tuple(
            argument.arg
            for argument in function.args.posonlyargs
            + function.args.args
            + function.args.kwonlyargs
        )
        annotation = ast.unparse(function.returns) if function.returns is not None else None
        components.append(
            ModelComponent(
                id=identifier,
                stage=stage,
                inputs=arguments,
                signature=ast.unparse(function.args),
                description=(ast.get_docstring(function) or "")[:4000],
                outputs=(annotation,) if annotation else (),
            )
        )
        for call in ast.walk(function):
            if not isinstance(call, ast.Call):
                continue
            target = None
            if isinstance(call.func, ast.Name):
                target = call.func.id
            elif isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                owner = call.func.value.id
                if owner in ("self", "cls") and "." in identifier:
                    owner = identifier.rsplit(".", 1)[0]
                target = owner + "." + call.func.attr
            if target in identifiers:
                dependencies.add((target, identifier))
        if any(isinstance(node, (ast.For, ast.While, ast.AsyncFor)) for node in ast.walk(function)):
            warnings.append("internal iteration remains inside its component")
    result = tuple(components)
    edges = tuple(sorted(dependencies))
    validate_dependencies(result, edges)
    return result, edges, tuple(sorted(set(warnings)))


def cli_arguments(argv: tuple[str, ...]) -> dict[str, str | bool]:
    if not argv or any(len(argument) > 4096 for argument in argv):
        raise ConstraintError("bounded declared CLI arguments are required")
    output: dict[str, str | bool] = {}
    index = 1
    while index < len(argv):
        argument = argv[index]
        if argument.startswith("--") and len(argument) > 2:
            name, separator, value = argument[2:].partition("=")
            if name in output:
                raise ConstraintError("repeated CLI option requires a declared multi-value schema")
            if separator:
                output[name] = value
            elif index + 1 < len(argv) and not argv[index + 1].startswith("--"):
                output[name] = argv[index + 1]
                index += 1
            else:
                output[name] = True
        else:
            output[f"positional_{index}"] = argument
        index += 1
    return output


def decompose_model(request: DecompositionRequest) -> ModelDecomposition:
    if request.kind == "black_box":
        return ModelDecomposition(
            model_name=request.name,
            mode="BLACK_BOX",
            components=(ModelComponent(id=request.name, stage="compute", atomic=True),),
            dependencies=(),
            warnings=("scientific internals are not modified or inferred",),
        )
    if request.kind == "python":
        if not request.source:
            raise ConstraintError("Python source is required for static inspection")
        components, dependencies, warnings = python_components(request.source)
        return ModelDecomposition(
            model_name=request.name,
            mode="WHITE_BOX",
            components=components,
            dependencies=dependencies,
            warnings=warnings,
        )
    if request.kind == "cli":
        return ModelDecomposition(
            model_name=request.name,
            mode="WHITE_BOX",
            components=(ModelComponent(id=request.name, stage="compute", atomic=True),),
            dependencies=(),
            cli_arguments=cli_arguments(request.argv),
            warnings=("CLI options are metadata; executable internals remain atomic",),
        )
    validate_dependencies(request.components, request.dependencies)
    return ModelDecomposition(
        model_name=request.name,
        mode="WHITE_BOX",
        components=request.components,
        dependencies=request.dependencies,
    )
