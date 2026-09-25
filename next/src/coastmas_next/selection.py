"""One interpretation of task-selected layers and identity fields across consumers."""

from .store import Problem


def selected_layer(asset, draft):
    references = [ref for ref in draft["selection"] if ref["asset_id"] == asset["id"]]
    if len(references) != 1:
        raise Problem(422, "SOURCE_SELECTION", "同一资料需要唯一明确的本次图层选择")
    layers = asset["facts"]["layers"]
    selected = references[0].get("layer")
    if not selected and len(layers) != 1:
        raise Problem(422, "LAYER_REQUIRED", "请选择实际资料中的一个图层")
    selected = selected or layers[0]["name"]
    found = next((layer for layer in layers if layer["name"] == selected), None)
    if found is None:
        raise Problem(422, "LAYER_MISSING", "所选图层不在实际资料中")
    return found


def identity_field(asset, draft, layer):
    identities = [
        b
        for b in draft["mapping"]
        if b["asset_id"] == asset["id"]
        and b["role"] == "identity"
        and b["field"].startswith(layer["name"] + "/")
    ]
    if len(identities) > 1:
        raise Problem(422, "IDENTITY_AMBIGUOUS", "请选择唯一实体标识字段")
    if not identities:
        return None
    found = next(
        (
            field["name"]
            for field in layer["fields"]
            if layer["name"] + "/" + field["name"] == identities[0]["field"]
        ),
        None,
    )
    if found is None:
        raise Problem(422, "BINDING_INVALID", "标识字段不在实际资料中")
    return found
