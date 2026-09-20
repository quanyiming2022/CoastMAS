"""Stable error codes; callers add request IDs without exposing secrets."""

from pydantic import JsonValue


class CoastMASError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, JsonValue] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ConstraintError(CoastMASError):
    def __init__(self, message: str, details: dict[str, JsonValue] | None = None):
        super().__init__("CONSTRAINT_ERROR", message, details)
