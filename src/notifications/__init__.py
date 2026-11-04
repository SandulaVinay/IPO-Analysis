"""
Notifications module exports.
"""

from importlib import import_module

_EXPORTS = {
    "NotificationProvider": "provider",
    "WhatsAppProvider": "whatsapp",
    "EmailProvider": "email",
    "SMSProvider": "sms",
    "ConsoleProvider": "console",
    "NotificationOrchestrator": "orchestrator",
    "SystemScheduler": "scheduler",
}


def __getattr__(name):
    """Load provider exports lazily so notification imports do not pull in the scheduler."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, name)


def __dir__():
    return sorted(set(globals()) | set(__all__))

__all__ = [
    "NotificationProvider",
    "WhatsAppProvider",
    "EmailProvider",
    "SMSProvider",
    "ConsoleProvider",
    "NotificationOrchestrator",
    "SystemScheduler",
]
