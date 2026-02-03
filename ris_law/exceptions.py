class RisLawError(Exception):
    """Base error for ris-law."""


class RisFetchError(RisLawError):
    """Raised when a network fetch fails."""


class RisParseError(RisLawError):
    """Raised when parsing HTML or data fails."""


class RisSoapError(RisLawError):
    """Raised when SOAP calls fail."""
