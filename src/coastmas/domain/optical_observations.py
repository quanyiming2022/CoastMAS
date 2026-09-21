"""Bounded, aligned acquisitions: no implied coverage between satellite overpasses."""

from typing import Annotated, Self

from pydantic import AwareDatetime, Field, FiniteFloat, model_validator

from coastmas.core.contracts import Contract, Name, TargetGridSpec

Row = Annotated[tuple[FiniteFloat | None, ...], Field(min_length=1, max_length=512)]
Band = Annotated[tuple[Row, ...], Field(min_length=1, max_length=512)]


class OpticalObservation(Contract):
    acquired_at: AwareDatetime
    grid: TargetGridSpec
    nir: Band
    red: Band
    source_item: Name

    @model_validator(mode="after")
    def aligned(self) -> Self:
        if self.grid.width * self.grid.height > 250000:
            raise ValueError("optical observation exceeds cell budget")
        for band in (self.nir, self.red):
            if len(band) != self.grid.height or any(len(row) != self.grid.width for row in band):
                raise ValueError("optical band shape differs from its declared grid")
        return self


class OpticalPair(Contract):
    frames: tuple[OpticalObservation, OpticalObservation]

    @model_validator(mode="after")
    def comparable(self) -> Self:
        before, after = self.frames
        if before.acquired_at >= after.acquired_at:
            raise ValueError("two distinct, ordered acquisitions are required")
        if before.grid != after.grid:
            raise ValueError("observations require identical grids; alignment must be explicit")
        return self
