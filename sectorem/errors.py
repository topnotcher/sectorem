"""Sectorem exception hierarchy."""


class SectoremError(Exception):
    """Base exception for all sectorem errors."""


class NotAuthenticatedError(SectoremError):
    """Raised when an operation requires authentication but none is active."""


class AuthenticationError(SectoremError):
    """Raised when an authentication operation fails."""
