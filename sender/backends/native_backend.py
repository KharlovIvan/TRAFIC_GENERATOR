"""Native (Rust/C++) sender backend adapter.

This module bridges between the Python ``SenderBackend`` interface and
the native extension module ``trafic_native``.  Schema/config data is
flattened into simple types before crossing the FFI boundary.

The native backend uses Npcap (Windows) or libpcap (Linux) for real L2
Ethernet frame transmission.  If the pcap library is not installed,
``validate_environment()`` reports the issue and ``initialize()`` raises.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any, Callable

from common.enums import GenerationMode
from common.metrics import SenderMetrics
from common.schema_models import PacketSchema
from common.utils import flatten_fields_in_layout_order
from sender.backends.base import SenderBackend
from sender.sender_config import SenderConfig

log = logging.getLogger(__name__)

# Module-level cache so we avoid repeated import attempts.
_NATIVE_MODULE: object | None = None
_NATIVE_IMPORT_ERROR: str | None = None


def _try_import_native() -> tuple[object | None, str | None]:
    """Attempt to import the native extension once."""
    global _NATIVE_MODULE, _NATIVE_IMPORT_ERROR  # noqa: PLW0603
    if _NATIVE_MODULE is not None:
        return _NATIVE_MODULE, None
    if _NATIVE_IMPORT_ERROR is not None:
        return None, _NATIVE_IMPORT_ERROR
    try:
        import trafic_native  # type: ignore[import-not-found]

        _NATIVE_MODULE = trafic_native
        return trafic_native, None
    except ImportError as exc:
        _NATIVE_IMPORT_ERROR = str(exc)
        return None, _NATIVE_IMPORT_ERROR


def reset_native_cache() -> None:
    """Reset the cached import state.  Useful for tests."""
    global _NATIVE_MODULE, _NATIVE_IMPORT_ERROR  # noqa: PLW0603
    _NATIVE_MODULE = None
    _NATIVE_IMPORT_ERROR = None


def is_native_available() -> bool:
    """Return ``True`` if the native extension is importable."""
    mod, _ = _try_import_native()
    return mod is not None


def is_native_transport_available() -> bool:
    """Return ``True`` if the native extension AND real NIC transport are available."""
    mod, _ = _try_import_native()
    if mod is None:
        return False
    try:
        return mod.is_transport_available()  # type: ignore[union-attr]
    except (AttributeError, Exception):
        return False


def list_native_interfaces() -> list[tuple[str, str]]:
    """Return list of ``(device_name, description)`` from pcap.

    Returns an empty list if the native module or transport is unavailable.
    """
    mod, _ = _try_import_native()
    if mod is None:
        return []
    try:
        return mod.list_interfaces()  # type: ignore[union-attr]
    except (AttributeError, Exception):
        return []


# ---- Windows friendly-name → pcap device resolution --------------------


def _resolve_windows_friendly_name(friendly_name: str) -> str | None:
    """Map a Windows friendly adapter name (e.g. 'Ethernet') to ``\\Device\\NPF_{GUID}``.

    Uses the Windows registry to look up the adapter GUID associated with
    the given friendly name under the network class key.
    Returns ``None`` on non-Windows systems or if no match is found.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    # Windows stores adapter-to-friendly-name mapping here:
    # HKLM\SYSTEM\CurrentControlSet\Control\Network\{4D36E972-...}\{GUID}\Connection
    #   Name = "Ethernet"
    net_class = r"SYSTEM\CurrentControlSet\Control\Network\{4D36E972-E325-11CE-BFC1-08002BE10318}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, net_class) as net_key:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(net_key, i)
                    i += 1
                except OSError:
                    break
                try:
                    conn_path = f"{net_class}\\{subkey_name}\\Connection"
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, conn_path) as conn_key:
                        name, _ = winreg.QueryValueEx(conn_key, "Name")
                        if name.lower() == friendly_name.lower():
                            return f"\\Device\\NPF_{subkey_name}"
                except OSError:
                    continue
    except OSError:
        pass
    return None


def _resolve_interface_to_pcap(
    interface: str,
    pcap_interfaces: list[tuple[str, str]],
) -> str:
    """Resolve a user-friendly interface name to a pcap device name.

    On Windows, friendly names like ``Ethernet`` or ``Wi-Fi`` differ from
    pcap device names (``\\Device\\NPF_{GUID}``).  This function bridges
    the gap:

    1. Already a pcap device name → return as-is.
    2. Exact match on pcap name or description → use that device.
    3. Substring match on pcap description → use that device.
    4. Windows registry lookup for the friendly name → GUID.
    5. Fallback: return unchanged.
    """
    # 1. Already a pcap device path
    if interface.startswith("\\Device\\"):
        return interface

    iface_lower = interface.lower()

    # 2. Exact match on pcap name or description
    for name, desc in pcap_interfaces:
        if iface_lower == name.lower() or iface_lower == desc.lower():
            return name

    # 3. Substring match on pcap description
    for name, desc in pcap_interfaces:
        if desc and iface_lower in desc.lower():
            return name

    # 4. Windows registry lookup
    resolved = _resolve_windows_friendly_name(interface)
    if resolved:
        log.info(
            "Resolved interface '%s' → '%s' via Windows registry.",
            interface,
            resolved,
        )
        return resolved

    # 5. Fallback
    return interface


# ---- Schema / config flattening for FFI --------------------------------


def flatten_schema_for_native(schema: PacketSchema) -> list[dict[str, Any]]:
    """Flatten a :class:`PacketSchema` into a list of field descriptors.

    Each descriptor is a plain dict suitable for passing across FFI:
    ``{"name": str, "type": str, "bit_length": int}``.
    """
    return [
        {
            "name": f.name,
            "type": f.type.value,
            "bit_length": f.bit_length,
        }
        for f in flatten_fields_in_layout_order(schema)
    ]


def flatten_config_for_native(
    config: SenderConfig,
    schema: PacketSchema,
    fixed_values: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a plain-dict config blob for the native sender.

    The output format matches what the Rust ``parse_config`` function
    expects.
    """
    fixed_vals: dict[str, Any] = {}
    if fixed_values is not None:
        for k, v in fixed_values.items():
            if isinstance(v, bytes):
                fixed_vals[k] = v.hex()
            else:
                fixed_vals[k] = v

    return {
        "interface": config.interface,
        "dst_mac": SenderConfig.normalize_mac(config.dst_mac),
        "src_mac": SenderConfig.normalize_mac(config.src_mac),
        "ethertype": config.ethertype,
        "stream_id": config.stream_id,
        "pps": config.packets_per_second,
        "packet_count": config.packet_count,
        "duration_sec": config.duration_seconds,
        "generation_mode": config.generation_mode.value,
        "fields": flatten_schema_for_native(schema),
        "fixed_values": fixed_vals,
    }


def _native_metrics_to_python(
    raw: dict[str, Any],
    start_time: float = 0.0,
) -> SenderMetrics:
    """Convert a dict returned by the native module into a :class:`SenderMetrics`."""
    m = SenderMetrics()
    m.packets_attempted = int(raw.get("packets_attempted", 0))
    m.packets_sent = int(raw.get("packets_sent", 0))
    m.packets_failed = int(raw.get("packets_failed", 0))
    m.bytes_sent = int(raw.get("bytes_sent", 0))
    m.first_tx_timestamp_ns = int(raw.get("first_tx_timestamp_ns", 0))
    m.last_tx_timestamp_ns = int(raw.get("last_tx_timestamp_ns", 0))
    m.start_time = start_time
    m.last_update_time = time.monotonic()
    return m


# ---- Backend implementation --------------------------------------------


class NativeSenderBackend(SenderBackend):
    """Sender backend that delegates to a native Rust/C++ extension.

    Uses Npcap/libpcap for real L2 Ethernet frame transmission.
    If the native module or pcap library is not available,
    :meth:`validate_environment` returns clear errors and
    :meth:`initialize` raises.
    """

    def __init__(self) -> None:
        self._handle: int | None = None
        self._config_dict: dict[str, Any] | None = None
        self._metrics = SenderMetrics()
        self._running = False

    def initialize(
        self,
        config: SenderConfig,
        schema: PacketSchema,
        fixed_values: dict[str, Any] | None = None,
    ) -> None:
        mod, err = _try_import_native()
        if mod is None:
            raise RuntimeError(f"Native backend is not available: {err}")

        # Reject RANDOM mode early with a clear message
        if config.generation_mode is GenerationMode.RANDOM:
            raise RuntimeError(
                "RANDOM generation mode is not yet supported in the native backend. "
                "Use FIXED mode or switch to the Python backend."
            )

        # Validate transport availability
        try:
            transport_ok = mod.is_transport_available()  # type: ignore[union-attr]
        except (AttributeError, Exception):
            transport_ok = False

        if not transport_ok:
            raise RuntimeError(
                "Native real NIC transport is not available. "
                "Install Npcap from https://npcap.com and restart."
            )

        # Validate interface exists on the system
        try:
            interfaces = mod.list_interfaces()  # type: ignore[union-attr]
            iface_lower = config.interface.lower()
            found = any(
                iface_lower in name.lower() or iface_lower in desc.lower()
                for name, desc in interfaces
            )
            if not found and interfaces:
                available = ", ".join(
                    f"{desc} ({name})" if desc else name
                    for name, desc in interfaces
                )
                log.warning(
                    "Interface '%s' not found in pcap device list. "
                    "Available: %s. Will attempt open anyway.",
                    config.interface,
                    available,
                )
        except (AttributeError, Exception) as exc:
            log.warning("Could not enumerate interfaces: %s", exc)

        native_cfg = flatten_config_for_native(config, schema, fixed_values)

        # Resolve the user-friendly name to an actual pcap device name.
        pcap_ifaces = list_native_interfaces()
        resolved = _resolve_interface_to_pcap(config.interface, pcap_ifaces)
        if resolved != config.interface:
            log.info(
                "Resolved interface '%s' → '%s'",
                config.interface,
                resolved,
            )
        native_cfg["interface"] = resolved

        self._config_dict = native_cfg
        # use_loopback=False → real NIC transport
        self._handle = mod.create_sender(native_cfg, False)  # type: ignore[union-attr]
        self._metrics = SenderMetrics()
        log.info(
            "Native sender initialized: interface=%s, transport=NpcapTransport",
            resolved,
        )

    def start(
        self,
        on_progress: Callable[[SenderMetrics], None] | None = None,
        progress_interval: float = 0.25,
    ) -> SenderMetrics:
        mod, _ = _try_import_native()
        if mod is None or self._handle is None:
            raise RuntimeError("Native backend not initialized.")

        self._running = True
        handle = self._handle
        send_error: BaseException | None = None
        final_metrics: dict[str, Any] = {}
        start_mono = time.monotonic()
        log.info("Native sender started (real NIC transport).")

        def _run_sender() -> None:
            nonlocal send_error, final_metrics
            try:
                final_metrics = mod.start_sender(handle, progress_interval)  # type: ignore[union-attr]
            except BaseException as exc:
                send_error = exc

        sender_thread = threading.Thread(target=_run_sender, daemon=True)
        sender_thread.start()

        try:
            # Poll metrics while the sender is running
            while sender_thread.is_alive():
                sender_thread.join(timeout=progress_interval)
                if self._handle is not None:
                    try:
                        raw = mod.get_sender_metrics(handle)  # type: ignore[union-attr]
                        self._metrics = _native_metrics_to_python(raw, start_mono)
                        if on_progress:
                            on_progress(self._metrics)
                    except Exception:
                        pass

            # Sender finished — collect final metrics
            if final_metrics:
                self._metrics = _native_metrics_to_python(final_metrics, start_mono)
            if on_progress:
                on_progress(self._metrics)

            if send_error is not None:
                raise send_error
        finally:
            self._running = False
            self._cleanup_handle()

        log.info(
            "Native sender finished: attempted=%d, sent=%d, failed=%d, bytes=%d",
            self._metrics.packets_attempted,
            self._metrics.packets_sent,
            self._metrics.packets_failed,
            self._metrics.bytes_sent,
        )
        return self._metrics

    def stop(self) -> None:
        mod, _ = _try_import_native()
        if mod is not None and self._handle is not None:
            mod.stop_sender(self._handle)  # type: ignore[union-attr]

    def is_running(self) -> bool:
        return self._running

    def get_metrics(self) -> SenderMetrics:
        return self._metrics

    def _cleanup_handle(self) -> None:
        """Destroy the native sender handle if it exists."""
        mod, _ = _try_import_native()
        if mod is not None and self._handle is not None:
            try:
                mod.destroy_sender(self._handle)  # type: ignore[union-attr]
            except Exception:
                pass
            self._handle = None

    @classmethod
    def validate_environment(cls) -> list[str]:
        errors: list[str] = []
        mod, err = _try_import_native()
        if err is not None:
            errors.append(f"Native extension not available: {err}")
            return errors
        # Check real transport
        try:
            if not mod.is_transport_available():  # type: ignore[union-attr]
                errors.append(
                    "Npcap/libpcap not found — real NIC transmission unavailable. "
                    "Install Npcap from https://npcap.com"
                )
        except (AttributeError, Exception):
            errors.append(
                "Native module does not expose transport validation. Rebuild required."
            )
        return errors

    @classmethod
    def get_backend_name(cls) -> str:
        return "Native (Rust/C++)"
