"""Load world exports on demand, without unrelated world dependencies."""

from importlib import import_module

_MODULES = {
    "Automation": "automation", "Communication": "communication",
    "Configurations": "configurations", "CRUD": "crud",
    "DesktopManager": "desktop_manager", "EventsScheduler": "events_scheduler",
    "FileManagement": "file_management", "LegalCompliance": "legal_compliance",
    "Computations": "computations", "Navigation": "navigation",
    "Transactions": "transactions", "Validation": "validation",
    "WebBrowsing": "web_browsing", "Writing": "writing",
}
__all__ = list(_MODULES)


def __getattr__(name):
    if name not in _MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    result = getattr(import_module(f"{__name__}.{_MODULES[name]}"), name)
    globals()[name] = result
    return result
