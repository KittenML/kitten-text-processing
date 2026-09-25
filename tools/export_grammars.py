"""Build-time only: export NeMo 1.2.0 graphs into portable numeric arrays."""
import argparse
from array import array
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import struct
import sys

LANGUAGES = 'en es fr de pt it zh ja ko hi ar ru vi hu sv hy rw'.split()
ROOT = Path(__file__).resolve().parents[1]


def export(fst, path):
    offsets, labels, targets, weights, finals = (array(t) for t in ('I', 'I', 'I', 'f', 'f'))
    for state in fst.states():
        offsets.append(len(labels))
        finals.append(float(fst.final(state)))
        for arc in fst.arcs(state):
            if arc.ilabel > 255 or arc.olabel > 255:
                raise ValueError('Graph is not a byte transducer')
            labels.append(arc.ilabel | arc.olabel << 8)
            targets.append(arc.nextstate)
            weights.append(float(arc.weight))
    offsets.append(len(labels))
    header = struct.pack('<8sIII', b'KITTEN1\0', fst.start(), len(finals), len(labels))
    with path.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as out:
        out.write(header)
        for values in (offsets, finals, labels, targets, weights):
            if sys.byteorder != 'little':
                values.byteswap()
            out.write(values.tobytes())
    return {'states': len(finals), 'arcs': len(labels), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--languages', nargs='+', default=LANGUAGES, choices=LANGUAGES)
    args = parser.parse_args()
    from nemo_text_processing.text_normalization.normalize import Normalizer
    if importlib.metadata.version('nemo_text_processing') != '1.2.0':
        raise RuntimeError('Exporter requires nemo_text_processing==1.2.0')
    for lang in args.languages:
        folder = ROOT / 'kitten_text_processing' / 'data' / lang
        folder.mkdir(parents=True, exist_ok=True)
        if (folder / 'metadata.json').exists():
            print(f'{lang}: already exported', flush=True)
            continue
        n = Normalizer(input_case='cased', lang=lang, deterministic=lang != 'ru',
                       cache_dir=None if lang == 'rw' else str(ROOT / '.cache' / 'nemo' / lang))
        metadata = {'language': lang, 'nemo_version': '1.2.0', 'input_case': 'cased',
                    'deterministic': lang != 'ru', 'graphs': {}}
        if lang in ('ko', 'hy'):
            import pynini
            lower = Normalizer(input_case='lower_cased', lang=lang,
                               cache_dir=str(ROOT / '.cache' / 'nemo' / lang))
            assert pynini.equal(n.tagger.fst, lower.tagger.fst)
            assert pynini.equal(n.verbalizer.fst, lower.verbalizer.fst)
            metadata['input_cases'] = ['cased', 'lower_cased']
        for name, graph in [('tagger', n.tagger), ('verbalizer', n.verbalizer), ('post', n.post_processor)]:
            if graph is not None:
                metadata['graphs'][name] = export(graph.fst, folder / f'{name}.fst.gz')
                print(lang, name, metadata['graphs'][name], flush=True)
        (folder / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        del n

if __name__ == '__main__':
    main()
