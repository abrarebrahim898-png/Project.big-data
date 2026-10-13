from __future__ import annotations

import argparse
import csv
from pathlib import Path


def create_small_sample(input_file: str | Path, output_file: str | Path, rows: int = 100000) -> Path:
    """
    Extract a reproducible small sample from a large dirty CSV using streaming.
    Complies with Midterm Section 6.1:
    - Never loads the full file or list(reader) into memory.
    - Configurable row count from arguments.
    """
    src_path = Path(input_file).resolve()
    dst_path = Path(output_file).resolve()

    if not src_path.exists():
        raise FileNotFoundError(f"Input file not found: {src_path}")

    dst_path.parent.mkdir(parents=True, exist_ok=True)

    written_rows = 0
    with open(src_path, "r", encoding="utf-8-sig", newline="") as src:
        reader = csv.reader(src)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"Input file {src_path} is empty.")

        with open(dst_path, "w", encoding="utf-8", newline="") as dst:
            writer = csv.writer(dst)
            writer.writerow(header)

            for i, row in enumerate(reader, start=1):
                if i > rows:
                    break
                writer.writerow(row)
                written_rows += 1

    size_mb = round(dst_path.stat().st_size / (1024 * 1024), 4)
    print(f"Sample generated successfully:")
    print(f"Destination: {dst_path}")
    print(f"Rows written: {written_rows:,}")
    print(f"File size: {size_mb} MB")

    return dst_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a small sample from large dirty CSV via streaming")
    parser.add_argument("--input", required=True, help="Path to input large CSV file")
    parser.add_argument("--rows", type=int, default=100000, help="Number of rows to sample (default: 100,000)")
    parser.add_argument("--output", default="data/small_sample.csv", help="Output path (default: data/small_sample.csv)")
    args = parser.parse_args()

    create_small_sample(args.input, args.output, args.rows)
