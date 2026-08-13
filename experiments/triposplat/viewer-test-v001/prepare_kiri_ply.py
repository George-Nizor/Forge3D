"""Add the SH0 compatibility field required by KIRI's Blender importer.

TripoSplat emits a valid colour-only Gaussian PLY with no higher-order
spherical-harmonic fields. KIRI v4.1.5 nevertheless requires ``f_rest_0`` to
exist. This script preserves every original byte and appends a zero float to
each vertex record under that attribute name.
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path


def arguments() -> tuple[Path, Path]:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    if len(argv) != 2:
        raise SystemExit("usage: prepare_kiri_ply.py INPUT.ply OUTPUT.ply")
    return Path(argv[0]).resolve(), Path(argv[1]).resolve()


def main() -> None:
    source, destination = arguments()
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite {destination}")

    with source.open("rb") as stream:
        prefix = stream.read(16384)
        marker = b"end_header"
        marker_index = prefix.find(marker)
        if marker_index < 0:
            raise ValueError("PLY end_header marker was not found")
        newline_index = prefix.find(b"\n", marker_index)
        header_end = len(prefix) if newline_index < 0 else newline_index + 1
        header = prefix[:header_end]
        stream.seek(header_end)

        header_text = header.decode("ascii")
        if "format binary_little_endian 1.0" not in header_text:
            raise ValueError("Only binary_little_endian PLY input is supported")
        if re.search(r"^property float f_rest_0$", header_text, re.MULTILINE):
            raise ValueError("Input already contains f_rest_0; no conversion needed")

        count_match = re.search(r"^element vertex (\d+)$", header_text, re.MULTILINE)
        if not count_match:
            raise ValueError("PLY vertex count was not found")
        vertex_count = int(count_match.group(1))

        vertex_section = header_text.split("element vertex", 1)[1].split("end_header", 1)[0]
        property_lines = [line for line in vertex_section.splitlines() if line.startswith("property ")]
        if any(not line.startswith("property float ") for line in property_lines):
            raise ValueError("This converter expects float-only TripoSplat vertex records")
        record_size = len(property_lines) * 4
        expected_payload = vertex_count * record_size
        actual_payload = source.stat().st_size - header_end
        if actual_payload != expected_payload:
            raise ValueError(
                f"Unexpected PLY payload: expected {expected_payload} bytes, got {actual_payload}"
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        updated_header = header.replace(marker, b"property float f_rest_0\n" + marker, 1)
        zero = struct.pack("<f", 0.0)
        records_per_chunk = 8192

        with destination.open("xb") as output:
            output.write(updated_header)
            remaining = vertex_count
            while remaining:
                chunk_count = min(remaining, records_per_chunk)
                data = stream.read(chunk_count * record_size)
                if len(data) != chunk_count * record_size:
                    raise EOFError("PLY payload ended early")
                for offset in range(0, len(data), record_size):
                    output.write(data[offset : offset + record_size])
                    output.write(zero)
                remaining -= chunk_count

    print(
        f"Prepared {destination} with {vertex_count} vertices, "
        f"{record_size + 4} bytes per record"
    )


if __name__ == "__main__":
    main()
