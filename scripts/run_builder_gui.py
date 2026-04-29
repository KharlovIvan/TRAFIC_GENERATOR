"""Launch the XML Builder GUI."""

import sys
from pathlib import Path

# Ensure project root is on sys.path so imports work when running this script directly.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from builder.builder_gui import run_builder_gui

if __name__ == "__main__":
    run_builder_gui()
