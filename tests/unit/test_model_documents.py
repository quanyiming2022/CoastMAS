import json

import pytest

from coastmas.core.errors import CoastMASError
from coastmas.core.model_documents import export_model, import_model
from tests.factories import model


def test_json_and_yaml_model_documents_roundtrip_without_importing_code():
    source = model()
    for format in ("json", "yaml"):
        text = export_model(source, format)
        restored = import_model(text, format)
        assert restored.id == source.id
        assert restored.inputs == source.inputs
        assert restored.runtime_config == source.runtime_config
        assert restored.execution_status == "NOT_EXECUTABLE"
        assert restored.validation_status == "UNVALIDATED"


def test_ambiguous_duplicate_keys_and_yaml_aliases_are_rejected():
    payload = json.dumps(model().model_dump(mode="json"))
    payload = payload[:-1] + ',"id":"replacement"}'
    with pytest.raises(CoastMASError, match="duplicate"):
        import_model(payload, "json")
    with pytest.raises(CoastMASError, match="alias|anchor"):
        import_model("x: &values [1,2]\ny: *values", "yaml")
    with pytest.raises(CoastMASError, match="duplicate"):
        import_model("id: first\nid: second", "yaml")


def test_yaml_object_constructors_cannot_execute(tmp_path):
    marker = tmp_path / "do-not-create"
    payload = f'!!python/object/apply:os.system ["touch {marker}"]'
    with pytest.raises(CoastMASError):
        import_model(payload, "yaml")
    assert not marker.exists()


def test_model_documents_are_bounded_and_do_not_accept_embedded_secrets():
    with pytest.raises(CoastMASError, match="budget"):
        import_model("x" * 262145, "json")
    payload = model().model_dump(mode="json")
    payload["runtime_config"] = {"headers": {"api_key": "should-use-credential-reference"}}
    with pytest.raises(CoastMASError, match="credential"):
        import_model(json.dumps(payload), "json")
