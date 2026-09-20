"""Spatial indexes are derived from immutable source contracts in the same transaction."""

import json
from functools import partial

from pyproj import Transformer
from pyproj.exceptions import ProjError
from shapely.geometry import mapping, shape  # type: ignore[import-untyped]
from shapely.ops import transform  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.orm import Session

from coastmas.core.errors import ConstraintError
from coastmas.core.geography import GeographicEntity


def materialize_entity(session: Session, entity: GeographicEntity) -> None:
    try:
        transformer = Transformer.from_crs(
            entity.crs, "EPSG:4326", always_xy=True, allow_ballpark=False, only_best=True
        )
        geometry = transform(
            partial(transformer.transform, errcheck=True), shape(entity.geometry.model_dump())
        )
    except ProjError as exc:
        raise ConstraintError("entity coordinate transformation unavailable") from exc
    if geometry.is_empty or not geometry.is_valid:
        raise ConstraintError("entity geometry invalid after coordinate transformation")
    west, south, east, north = geometry.bounds
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ConstraintError("transformed entity outside longitude/latitude bounds")
    session.execute(
        text("""
        INSERT INTO geographic_entities(resource_id,version,geometry,valid_from,valid_to)
        VALUES(:identifier,:version,ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326),:start,:end)
        """),
        {
            "identifier": entity.id,
            "version": entity.version,
            "geometry": json.dumps(mapping(geometry), allow_nan=False),
            "start": entity.valid_from,
            "end": entity.valid_to,
        },
    )
