"""Prepare identical uncompressed grammar arrays for the dependency-free C++ runtime.

This build-time helper requires only Python's standard library. C++ applications
load the resulting files directly; no Python interpreter is used at runtime.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'kitten_text_processing/data')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for metadata_path in sorted(args.source.glob('*/metadata.json')):
        metadata = json.loads(metadata_path.read_text())
        destination = args.output / metadata['language']
        destination.mkdir(parents=True, exist_ok=True)
        for name, properties in metadata['graphs'].items():
            source = metadata_path.parent / f'{name}.fst.gz'
            compressed = source.read_bytes()
            if hashlib.sha256(compressed).hexdigest() != properties['sha256']:
                raise ValueError(f'Grammar checksum mismatch: {source}')
            output = destination / f'{name}.fst'
            raw = gzip.decompress(compressed)
            if not output.exists() or output.read_bytes() != raw:
                output.write_bytes(raw)
        (destination/'metadata.json').write_bytes(metadata_path.read_bytes())


if __name__ == '__main__':
    main()
