"""
Custom exceptions for the Indian IPO Intelligence System.
"""


class IPOIntelligenceError(Exception):
    """Base exception for all system errors."""
    pass


class DataUnavailableError(IPOIntelligenceError):
    """Raised when required verified data or filing is missing."""
    pass


class SafetyGateTriggeredError(IPOIntelligenceError):
    """Raised when hard safety gates prevent positive recommendation."""
    pass


class SourceConflictError(IPOIntelligenceError):
    """Raised when conflicting data from different sources is detected."""
    pass


class DocumentParsingError(IPOIntelligenceError):
    """Raised when PDF or table forensic parsing encounters an error."""
    pass


class NotificationDeliveryError(IPOIntelligenceError):
    """Raised when dispatching a notification across all channels fails."""
    pass


class ConfigurationError(IPOIntelligenceError):
    """Raised when critical configuration or secret is missing/invalid."""
    pass
