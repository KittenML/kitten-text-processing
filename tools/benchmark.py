"""Compare the standalone engine with NeMo, without modifying expected outputs.

Run with --record-reference in the separate NeMo environment once; subsequent
runs need only Python's standard library and use the checked-in snapshots.
"""
import argparse
from collections import defaultdict
import importlib.metadata
import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kitten_text_processing import Normalizer, SUPPORTED_LANGUAGES


def cases(languages=None):
    for path in sorted((ROOT / 'tests/corpus').glob('*.txt')):
        lang = path.stem
        if languages and lang not in languages:
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            category, text = line.split('|', 1)
            yield {'id': f'{lang}-{i:03}', 'lang': lang, 'category': category,
                   'input': text}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-reference', action='store_true')
    parser.add_argument('--languages', nargs='+', choices=SUPPORTED_LANGUAGES)
    parser.add_argument('--output', type=Path, default=ROOT/'benchmarks/latest.json')
    args = parser.parse_args()
    grouped = defaultdict(list)
    for case in cases(args.languages):
        grouped[case['lang']].append(case)
    all_results, summaries = [], {}
    for lang, items in grouped.items():
        snapshot = ROOT / 'tests/corpus' / f'{lang}.reference.json'
        if args.record_reference:
            from nemo_text_processing.text_normalization.normalize import Normalizer as Reference
            start = perf_counter()
            ref = Reference(input_case='cased', lang=lang, deterministic=lang != 'ru',
                            cache_dir=None if lang == 'rw' else str(ROOT/'.cache/nemo'/lang))
            load_seconds = perf_counter()-start
            records = []
            for item in items:
                start = perf_counter()
                try:
                    expected = ref.normalize(item['input'], punct_post_process=True)
                    error = None
                except Exception as exc:
                    expected, error = None, f'{type(exc).__name__}: {exc}'
                records.append(dict(item, expected=expected, reference_error=error,
                                    reference_seconds=perf_counter()-start))
            snapshot.write_text(json.dumps({'nemo_version': importlib.metadata.version('nemo_text_processing'),
                'pynini_version': importlib.metadata.version('pynini'),
                'sacremoses_version': importlib.metadata.version('sacremoses'),
                'load_seconds': load_seconds, 'cases': records}, ensure_ascii=False, indent=2)+'\n')
            del ref
        saved = json.loads(snapshot.read_text())
        records = saved['cases']
        if [(r['id'], r['input']) for r in records] != [(r['id'], r['input']) for r in items]:
            raise ValueError(f'Stale reference snapshot: {snapshot}')
        start = perf_counter()
        normalizer = Normalizer(lang=lang)
        load_seconds = perf_counter()-start
        results = []
        for record in records:
            start = perf_counter()
            try:
                actual = normalizer.normalize(record['input'], punct_post_process=True)
                error = None
            except Exception as exc:
                actual, error = None, f'{type(exc).__name__}: {exc}'
            row = dict(record, actual=actual, error=error, seconds=perf_counter()-start)
            row['same_error_outcome'] = error is not None and record['reference_error'] is not None
            row['exact_match'] = error is None and record['reference_error'] is None and actual == record['expected']
            results.append(row)
        summaries[lang] = {'cases': len(results), 'exact_matches': sum(r['exact_match'] for r in results),
            'reference_errors': sum(r['reference_error'] is not None for r in results),
            'errors': sum(r['error'] is not None for r in results),
            'same_error_outcomes': sum(r['same_error_outcome'] for r in results),
            'accepted_cases': sum(r['reference_error'] is None for r in results),
            'load_seconds': load_seconds,
            'median_ms': 1000*statistics.median(r['seconds'] for r in results),
            'reference_median_ms': 1000*statistics.median(r['reference_seconds'] for r in results)}
        all_results.extend(results)
        print(lang, summaries[lang], flush=True)
        # Save incrementally so interrupted runs retain completed languages.
        report = {'python': platform.python_version(), 'platform': platform.platform(),
                  'reference': 'nemo_text_processing==1.2.0', 'languages': summaries,
                  'cases': len(all_results), 'exact_matches': sum(r['exact_match'] for r in all_results),
                  'same_error_outcomes': sum(r['same_error_outcome'] for r in all_results),
                  'reference_errors': sum(r['reference_error'] is not None for r in all_results),
                  'mismatches': [r for r in all_results if not r['exact_match'] and not r['same_error_outcome']],
                  'upstream_failures': [r for r in all_results if r['reference_error'] is not None],
                  'results': all_results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        del normalizer
    return 1 if report['mismatches'] else 0

if __name__ == '__main__':
    sys.exit(main())
