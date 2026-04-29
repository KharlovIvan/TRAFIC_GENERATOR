"""Field type enumerations for the packet schema."""

from enum import Enum


class FieldType(Enum):
    """Supported field types for the MVP schema format."""

    INTEGER = "INTEGER"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    RAW_BYTES = "RAW_BYTES"

    @classmethod
    def from_string(cls, value: str) -> "FieldType":
        """Convert a string to a FieldType enum member.

        Raises:
            ValueError: If the string does not match any supported field type.
        """
        try:
            return cls(value.upper().strip())
        except ValueError:
            valid = ", ".join(member.value for member in cls)
            raise ValueError(
                f"Unsupported field type '{value}'. Valid types: {valid}"
            ) from None

    def to_string(self) -> str:
        """Return the string representation of this field type."""
        return self.value


class GenerationMode(Enum):
    """How field values are generated for each packet."""

    FIXED = "FIXED"
    RANDOM = "RANDOM"


class ExportFormat(Enum):
    """Output format for captured traffic."""

    PCAP = "pcap"
    JSON = "json"
    PCAP_AND_JSON = "pcap+json"


class BackendMode(Enum):
    """Which sender/receiver backend implementation to use."""

    PYTHON = "PYTHON"
    NATIVE = "NATIVE"
