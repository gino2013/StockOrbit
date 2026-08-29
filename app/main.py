"""ASGI entrypoint. Real wiring lives in the interface layer."""
from app.interface.http import app

__all__ = ["app"]
