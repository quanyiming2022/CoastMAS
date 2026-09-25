"""Apply frozen indicator definitions to aligned observations, without new algorithms."""

import numpy as np

from coastmas.adapters.projection_pursuit import ProjectionFrame
from coastmas.core.errors import ConstraintError
from coastmas.core.indicators import IndicatorFrameworkSpec
from coastmas.domain.indicator_frames import IndicatorFrame, normalize_frame
from coastmas.domain.raster_units import calculate_arrays


def apply_framework(
    framework: IndicatorFrameworkSpec, observations: IndicatorFrame | ProjectionFrame
) -> IndicatorFrame:
    values = np.asarray(observations.values, dtype=float)
    if values.size > 1_000_000:
        raise ConstraintError("indicator observation budget exceeds one million values")
    periods = values[None, ...] if values.ndim == 2 else values
    if periods.shape[0] * periods.shape[1] * len(framework.indicators) > 1_000_000:
        raise ConstraintError("derived indicator budget exceeds one million values")
    if isinstance(observations, ProjectionFrame):
        if framework.spatial_support != "grid" or observations.response is not None:
            raise ConstraintError(
                "raster observation preparation requires a grid framework and no response"
            )
        names, units = observations.feature_names, observations.feature_units
        unit_ids, years = observations.row_ids, None
    else:
        names = tuple(column.name for column in observations.columns)
        units = tuple(column.unit for column in observations.columns)
        unit_ids, years = observations.unit_ids, observations.years
    lookup = {name: index for index, name in enumerate(names)}
    outputs = []
    columns = []
    for indicator in framework.indicators:
        inputs = {}
        for alias, column_name in indicator.source.items():
            if column_name not in lookup:
                raise ConstraintError(
                    "indicator source column is unavailable", {"column": column_name}
                )
            index = lookup[column_name]
            inputs[alias] = (periods[:, :, index], units[index])
        outputs.append(calculate_arrays(indicator.formula, inputs, indicator.unit))
        columns.append(
            {
                "name": indicator.indicator_id,
                "unit": indicator.unit,
                "reference_unit": indicator.unit,
                "lower": indicator.normalization.lower,
                "upper": indicator.normalization.upper,
                "positive": indicator.direction == "positive",
                "weight": indicator.weight if indicator.weight is not None else 1,
            }
        )
    derived = np.stack(outputs, axis=-1)
    result = IndicatorFrame.model_validate(
        {
            "unit_ids": unit_ids,
            "years": years,
            "columns": columns,
            "values": (derived[0] if years is None else derived).tolist(),
            "class_breaks": framework.class_breaks,
        }
    )
    # Reject out-of-reference values at preparation time, not after a queued run.
    normalize_frame(result)
    return result
