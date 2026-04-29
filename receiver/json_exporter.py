"""JSON Lines exporter – incremental per-packet export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import IO

from common.exceptions import ExportError


class JsonExporter:
    """Write parsed packet records as JSON Lines (.jsonl)."""

    def __init__(self) -> None:
        self._file: IO[str] | None = None

    def start(self, path: str) -> None:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._file = open(path, "w", encoding="utf-8")
        except Exception as exc:
            raise ExportError(f"Cannot open JSON output: {exc}") from exc

    def write(self, record: dict[str, object]) -> None:
        if self._file is None:
            raise ExportError("JsonExporter not started.")
        line = json.dumps(record, ensure_ascii=False, default=str)
        self._file.write(line + "\n")
        self._file.flush()

    def stop(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
