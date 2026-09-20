from pathlib import Path

import pytest

from coastmas.core.errors import CoastMASError
from coastmas.domain.coastal_catalog import coastal_catalog
from coastmas.runtime_bootstrap import BuiltinRuntimeRegistry


def test_builtin_runtime_recognizes_lifecycle_versions_but_not_scientific_edits():
    registry = BuiltinRuntimeRegistry(Path("sample-data"))
    source = coastal_catalog("runtime-project", Path("sample-data")).models[0]
    revised = source.model_copy(update={"version": 3, "enabled": True})
    assert registry.resolve(revised).handler == registry.resolve(source).handler
    forged = revised.model_copy(update={"description": "different scientific contract"})
    with pytest.raises(CoastMASError):
        registry.resolve(forged)
    unknown = revised.model_copy(update={"id": "external:runtime-project:normalize"})
    with pytest.raises(CoastMASError):
        registry.resolve(unknown)
