"""CLI receiver – argparse-based command-line interface."""

from __future__ import annotations

import argparse
import signal
import sys
import time

from common.enums import ExportFormat
from common.metrics import ReceiverMetrics
from receiver.receiver_config import ReceiverConfig
from receiver.receiver_service import ReceiverService


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="receiver",
        description="Traffic Generator – Receiver CLI",
    )
    p.add_argument("--iface", required=True, help="Network interface name")
    p.add_argument("--schema", required=True, help="Path to XML schema file")
    p.add_argument(
        "--ethertype",
        default="0x88B5",
        help="EtherType filter (hex or decimal, default 0x88B5)",
    )
    p.add_argument(
        "--export-format",
        choices=["pcap", "json", "pcap+json"],
        default="pcap+json",
        help="Output format (default: pcap+json)",
    )
    p.add_argument("--pcap-out", default=None, help="PCAP output file path")
    p.add_argument("--json-out", default=None, help="JSONL output file path")
    p.add_argument(
        "--duration", type=float, default=None, help="Capture duration in seconds"
    )
    p.add_argument(
        "--packet-limit", type=int, default=None, help="Max packets to capture"
    )
    p.add_argument(
        "--no-promisc",
        action="store_true",
        help="Disable promiscuous mode",
    )
    return p.parse_args(argv)


def _parse_ethertype(text: str) -> int:
    text = text.strip()
    if text.startswith(("0x", "0X")):
        return int(text, 16)
    return int(text)


def _print_progress(metrics: ReceiverMetrics) -> None:
    snap = metrics.snapshot()
    sys.stdout.write(
        f"\r  pkts={snap['packets_received']}  "
        f"ok={snap['packets_parsed_ok']}  "
        f"invalid={snap['packets_invalid']}  "
        f"bytes={snap['bytes_received']}  "
        f"elapsed={snap['elapsed_seconds']}s  "
        f"pps={snap['pps']}  "
        f"Gbps={snap['average_gbps']}"
    )
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        ethertype = _parse_ethertype(args.ethertype)
    except ValueError:
        print(f"Error: invalid EtherType '{args.ethertype}'", file=sys.stderr)
        return 1

    config = ReceiverConfig(
        interface_name=args.iface,
        ethertype=ethertype,
        schema_path=args.schema,
        export_format=ExportFormat(args.export_format),
        pcap_output_path=args.pcap_out,
        json_output_path=args.json_out,
        duration_sec=args.duration,
        packet_limit=args.packet_limit,
        promiscuous=not args.no_promisc,
    )

    errors = config.validate()
    if errors:
        for e in errors:
            print(f"Config error: {e}", file=sys.stderr)
        return 1

    service = ReceiverService()

    # Load schema
    try:
        schema = service.load_schema(config.schema_path)
    except Exception as exc:
        print(f"Schema error: {exc}", file=sys.stderr)
        return 1

    warnings = service.validate_schema_for_receive()
    if warnings:
        for w in warnings:
            print(f"Schema warning: {w}", file=sys.stderr)
        print("Capture blocked due to schema semantic errors.", file=sys.stderr)
        return 1

    summary = service.schema_summary()
    print(f"Schema: {summary.get('name')}  "
          f"fields={summary.get('field_count')}  "
          f"payload={summary.get('payload_bytes')} bytes")

    # Handle Ctrl+C
    def _sigint(sig, frame):
        print("\nStopping capture …")
        service.stop()

    signal.signal(signal.SIGINT, _sigint)

    print("Starting capture … (Ctrl+C to stop)")
    try:
        metrics = service.start(config, on_progress=_print_progress)
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    # Final summary
    snap = metrics.snapshot()
    print(f"\n\n=== Capture Summary ===")
    print(f"  Packets received:  {snap['packets_received']}")
    print(f"  Parsed OK:         {snap['packets_parsed_ok']}")
    print(f"  Invalid:           {snap['packets_invalid']}")
    print(f"  Bytes received:    {snap['bytes_received']}")
    print(f"  Duration:          {snap['elapsed_seconds']} s")
    print(f"  Avg PPS:           {snap['pps']}")
    print(f"  Avg Gbps:          {snap['average_gbps']}")
    print(f"  Unique streams:    {snap['unique_streams']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
