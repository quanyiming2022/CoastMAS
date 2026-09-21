"""Explicit optical reflectance calibration and normalized indices, preserving NoData."""

import numpy as np
from numpy.typing import ArrayLike

from coastmas.core.numeric import FloatArray


def calibrate_reflectance(
    values: ArrayLike, *, scale: float, offset: float, nodata: float
) -> FloatArray:
    raw = np.asarray(values, dtype=np.float64)
    if (
        raw.ndim != 2
        or not raw.size
        or not np.isfinite([scale, offset, nodata]).all()
        or scale <= 0
    ):
        raise ValueError("invalid reflectance array or calibration")
    output = raw * scale + offset
    output[(raw == nodata) | ~np.isfinite(raw)] = np.nan
    return output


def normalized_difference(positive: ArrayLike, negative: ArrayLike) -> FloatArray:
    left = np.asarray(positive, dtype=np.float64)
    right = np.asarray(negative, dtype=np.float64)
    if left.ndim != 2 or not left.size or left.shape != right.shape:
        raise ValueError("normalized difference requires aligned nonempty raster matrices")
    denominator = left + right
    valid = (
        np.isfinite(left) & np.isfinite(right) & (left >= 0) & (right >= 0) & (denominator > 1e-8)
    )
    result = np.full(left.shape, np.nan, dtype=np.float64)
    np.divide(left - right, denominator, out=result, where=valid)
    return result


def calibrated_cog_reflectance(
    values: ArrayLike,
    *,
    scale: float,
    offset: float,
    nodata: float,
    file_scale: float,
    file_offset: float,
    file_nodata: float | None,
) -> FloatArray:
    """Require independently stored COG calibration, refusing ambiguous legacy metadata."""
    if file_nodata is None or not np.allclose(
        [scale, offset, nodata],
        [file_scale, file_offset, file_nodata],
        rtol=0,
        atol=1e-12,
    ):
        raise ValueError("STAC and COG calibration metadata disagree; ingestion is blocked")
    return calibrate_reflectance(values, scale=scale, offset=offset, nodata=nodata)
