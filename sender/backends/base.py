"""Abstract base class for sender backends.

Every sender backend (Python, Rust, C++) must implement this interface.
``SenderService`` depends only on this abstraction, never on concrete
backend code directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from common.metrics import SenderMetrics
from common.schema_models import PacketSchema
from sender.sender_config import SenderConfig


class SenderBackend(ABC):
    """Unified interface for a sender backend.

    Lifecycle:
        1. ``initialize(config, schema, ...)``
        2. ``start(on_progress=...)``   – blocks until done / stopped
        3. ``stop()``                   – request graceful termination
        4. (repeat from 1 for next session)
    """

    @abstractmethod
    def initialize(
        self,
        config: SenderConfig,
        schema: PacketSchema,
        fixed_values: dict[str, Any] | None = None,
    ) -> None:
        """Prepare the backend for a sending session.

        Called once before :meth:`start`.  Implementations should
        validate that all required resources are available.
        """

    @abstractmethod
    def start(
        self,
        on_progress: Callable[[SenderMetrics], None] | None = None,
        progress_interval: float = 0.25,
    ) -> SenderMetrics:
        """Run the send loop.  Blocks until finished or :meth:`stop` is called.

        Returns final :class:`SenderMetrics` when the session ends.
        """

    @abstractmethod
    def stop(self) -> None:
        """Request the running session to stop as soon as possible."""

    @abstractmethod
    def is_running(self) -> bool:
        """Return ``True`` if a session is currently active."""

    @abstractmethod
    def get_metrics(self) -> SenderMetrics:
        """Return the current (or final) metrics for the session."""

    @classmethod
    @abstractmethod
    def validate_environment(cls) -> list[str]:
        """Check whether this backend can run in the current environment.

        Returns a list of human-readable error strings.  An empty list
        means the backend is ready to use.
        """

    @classmethod
    @abstractmethod
    def get_backend_name(cls) -> str:
        """Return a human-readable name for this backend."""
