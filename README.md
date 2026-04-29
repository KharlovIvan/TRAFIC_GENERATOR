# TRAFIC_GENERATOR

Traffic generator project – create, validate, send, and receive custom packet schemas.

## XML Builder

The XML Builder is a PySide6 desktop GUI for creating and editing packet XML schemas.

### Setup

```bash
pip install -r requirements.txt
```

### Run the Builder GUI

```bash
python scripts/run_builder_gui.py
```

### Run Tests

```bash
pytest tests/ -v
```

### Sample Schema

See `schemas/sample_packet.xml` for a complete example with nested headers.
