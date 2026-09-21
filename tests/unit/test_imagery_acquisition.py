"""Pinned public products cannot silently change when a STAC search order changes."""

import json

import httpx
import pytest

from scripts import prepare_real_imagery as acquisition


def product(identifier=None, collection="sentinel-2-c1-l2a"):
    return {"id": identifier or acquisition.ITEMS["yellow-river"], "collection": collection}


def test_fresh_install_fetches_exact_public_product_and_reuses_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(acquisition, "SEARCH_ROOT", tmp_path)
    calls = []

    def post(address, *, json, timeout):
        calls.append(json)
        return httpx.Response(
            200, json={"features": [product()]}, request=httpx.Request("POST", address)
        )

    monkeypatch.setattr(acquisition.httpx, "post", post)
    assert acquisition.source_item("yellow-river", "snapshot.json") == product()
    assert acquisition.source_item("yellow-river", "snapshot.json") == product()
    assert calls == [
        {
            "collections": ["sentinel-2-c1-l2a"],
            "ids": [acquisition.ITEMS["yellow-river"]],
            "limit": 1,
        }
    ]


def test_cached_snapshot_selects_identity_not_search_position(tmp_path, monkeypatch):
    monkeypatch.setattr(acquisition, "SEARCH_ROOT", tmp_path)
    (tmp_path / "snapshot.json").write_text(json.dumps({"features": [product("other"), product()]}))
    assert acquisition.source_item("yellow-river", "snapshot.json") == product()


@pytest.mark.parametrize(
    "features", [[product(), product()], [product(collection="sentinel-2-l2a")], [product("other")]]
)
def test_wrong_ambiguous_or_legacy_product_is_rejected(tmp_path, monkeypatch, features):
    monkeypatch.setattr(acquisition, "SEARCH_ROOT", tmp_path)
    (tmp_path / "snapshot.json").write_text(json.dumps({"features": features}))
    with pytest.raises(ValueError, match="exactly one pinned"):
        acquisition.source_item("yellow-river", "snapshot.json")
