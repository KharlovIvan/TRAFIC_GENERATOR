"""Custom exception types for the traffic generator project."""


class SchemaValidationError(Exception):
    """Raised when a schema fails validation rules.

    Attributes:
        errors: List of human-readable validation error messages.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        msg = "Schema validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(msg)


class SchemaParseError(Exception):
    """Raised when XML cannot be parsed into a valid schema structure."""


class BuilderOperationError(Exception):
    """Raised when a builder/editor operation fails."""


class SerializationError(Exception):
    """Raised when payload serialization fails."""


class SenderConfigError(Exception):
    """Raised when sender configuration is invalid."""


class SenderOperationError(Exception):
    """Raised when a sender operation fails at runtime."""


class ReceiverConfigError(Exception):
    """Raised when receiver configuration is invalid."""


class ReceiverOperationError(Exception):
    """Raised when a receiver operation fails at runtime."""


class PacketParseError(Exception):
    """Raised when a received packet cannot be parsed."""


class ExportError(Exception):
    """Raised when writing to an export file fails."""
