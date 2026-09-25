"""Seeded differential stress tests against NeMo 1.2.0 (development dependencies only).

One worker per language; each completed case is flushed to JSONL. Timeouts are
reported separately, never counted as matching errors. Replay needs no oracle.
"""
import argparse
from collections import Counter
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kitten_text_processing import Normalizer, SUPPORTED_LANGUAGES

UPSTREAM_COMMIT = '7efa127d968c081793ebf11fa94dfb4257302d48'


def inputs(lang, upstream, seed, count):
    seen = set()
    rows = []
    def add(text, source, options=None):
        options = options or {'punct_post_process': True}
        key = (text, json.dumps(options, sort_keys=True))
        if key not in seen:
            seen.add(key)
            rows.append({'id': f'{lang}-{len(rows):05}', 'lang': lang, 'input': text,
                         'source': source, 'options': options})

    if upstream:
        from upstream_cases import cases as upstream_cases
        for row in upstream_cases(lang):
            rows.append(row)
            seen.add((row['input'],json.dumps(row['options'],sort_keys=True)))

    edge = [
        '', ' ', '\t\n', '0', '-0', '+0', '00', '000000000000000000001',
        '999999999999999999999999999999', '1,00', '1,,000', '1.2.3.4', '.5', ',5',
        '1e10', '1E-10', '−12', '1\u2009234,56', '1\u00a0234.56',
        '١٢٣٫٤٥', '۱۲۳', '१२३.४५', '１２３．４５', '１２３', '2½', '½', '⅓',
        'NaN', 'Infinity', '-∞', '23:59:59', '24:00', '25:61', '00:00:00',
        '2000-02-29', '1900-02-29', '2025-13-40', '02/03/04', '1/0', '0/0',
        '$.50', '$-12.00', '-$12', '€1.234,56', '1,234.56 USD', '0.001 kg', '1m²',
        'http://a.co/x?q=1&v=2', 'a+b@example.co.uk', 'user_2@例子.中国',
        '[12]', '\\[12\\]', 'tokens { name: "12" }', 'C:\\temp\\12.txt',
        '"12"', "'12'", '«12»', '“12”', '„12“', '12?!', '12...34', '12—34',
        '1\t2', '1\n2', '1\r\n2', '1\u20282', '1\u20292', '1\x002', '\x00',
        'one\x00two', '1\x012', '1\x1b2', '1\x7f2', '1\u200b2', '1\u200d2',
        '\ufeff12', '12\u2060kg', '\u202e12\u202c', '😀 12 🐱', '👩🏽\u200d💻 2',
        'cafe\u0301 12', "word '\u0345word", "word '\u05b0word", '₿ 12',
        '\ue0000\ue001 12', '\ue00010\ue001 12', '\U0010ffff12', '\ud800',
        'I paid $12.50 for 3 books.', 'J\'ai payé 12,50 €.', '猫が2匹います。',
    ]
    for text in edge:
        add(text, 'edge')
    for text in ['[12] [3]', '"12"', '1\t2', '5 kg, $3.50!', '“2”\n[3]', '\\[12\\]']:
        for pre in (False, True):
            for post in (False, True):
                add(text, 'options', {'punct_pre_process': pre, 'punct_post_process': post})
    # Several independently composed sentences reach typical TTS chunk boundaries.
    sample = [line.split('|', 1)[1] for line in (ROOT/'tests/corpus'/f'{lang}.txt').read_text().splitlines()]
    for size in (2, 4, 8, 16):
        add(' '.join(sample[:size]), f'long:{size}')
    rng = random.Random(f'{seed}:{lang}')
    currencies = ['$', '€', '£', '¥', '₹', '₽', '₩', 'R$', 'USD ', 'EUR ', '₿']
    units = ['kg', 'km/h', 'm²', '°C', '°F', 'MHz', '%', 'ml', 'ft', 'm/s', 'GB', 'h', 'min']
    separators = [' ', '.', ',', '; ', '\n', '\t', '\u00a0', '-', '/', ':', '—']
    for i in range(count):
        n, m = rng.randint(0, 10**rng.randint(1, 10)), rng.randint(0, 999)
        kind = i % 10
        if kind == 0:
            text = rng.choice(['', '-', '+', '−']) + rng.choice([str(n), f'{n:,}', f'{n:015}'])
        elif kind == 1:
            text = str(n) + rng.choice(['.', ',']) + f'{m:03}'
        elif kind == 2:
            text = rng.choice(currencies) + str(n) + rng.choice(['.00', '.01', ',50', '.99', '', ' million'])
        elif kind == 3:
            text = f'{rng.randrange(32):02}:{rng.randrange(70):02}' + rng.choice(['', ' AM', ' p.m.', ':30', 'h'])
        elif kind == 4:
            text = f'{rng.randrange(1500,2100)}{rng.choice(["-", "/", "."])}{rng.randrange(1,16):02}/{rng.randrange(1,35):02}'
        elif kind == 5:
            text = f'{n}' + rng.choice([' ', '', '\u00a0']) + rng.choice(units)
        elif kind == 6:
            text = f'{n}/{m}' + rng.choice(['', ' kg', ' cups', ' %'])
        elif kind == 7:
            text = f'user{n}+{m}@example.co.uk' if rng.randrange(2) else f'https://a{n}.com/{m}?x=1'
        elif kind == 8:
            text = rng.choice(['a', 'v', 'AB', '第', '№']) + str(n) + rng.choice(['.2.3', 'st', 'th', '-B', '号'])
        else:
            text = str(n) + rng.choice(separators) + str(m)
        if i % 4 == 0:
            text = rng.choice(['"{}"', '[{}]', '({})', '«{}»', '{}?!', '{}...']).format(text)
        if i % 7 == 0:
            text = rng.choice(sample[:6]) + ' ' + text
        add(text, f'generated:{seed}')
    return rows


class CaseTimeout(BaseException):
    pass


def timeout_handler(signum, frame):
    raise CaseTimeout()


def call(normalizer, row, timeout):
    start = time.perf_counter()
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        value = normalizer.normalize(row['input'], **row['options'])
        return {'output': value, 'error': None, 'timeout': False, 'seconds': time.perf_counter()-start}
    except CaseTimeout:
        return {'output': None, 'error': 'timeout', 'timeout': True, 'seconds': time.perf_counter()-start}
    except Exception as exc:
        return {'output': None, 'error': type(exc).__name__ + ': ' + str(exc), 'timeout': False,
                'seconds': time.perf_counter()-start}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def status(reference, actual):
    if reference['timeout'] or actual['timeout']:
        return 'timeout'
    if reference['error']:
        return 'both_reject' if actual['error'] else 'reference_rejects_only'
    if actual['error']:
        return 'regression_error'
    return 'exact' if reference['output'] == actual['output'] else 'mismatch'


def worker(args):
    lang, rows, folder, timeout, replay = args
    signal.signal(signal.SIGALRM, timeout_handler)
    # Keep oracle logging out of progress output. All outcomes are persisted.
    errors = open(folder / f'{lang}.log', 'w')
    os.dup2(errors.fileno(), 2)
    normalizer = Normalizer(lang=lang)
    if not replay:
        from nemo_text_processing.text_normalization.normalize import Normalizer as Reference
        reference = Reference(input_case='cased', lang=lang, deterministic=lang != 'ru',
                              cache_dir=None if lang == 'rw' else str(ROOT/'.cache/nemo'/lang))
    models = {}
    references = {}
    counters = Counter()
    with (folder / f'{lang}.jsonl').open('w') as out:
        for row in rows:
            constructor = row.get('constructor_options', {})
            key = json.dumps(constructor,sort_keys=True)
            if key not in models:
                models[key] = normalizer if not constructor else Normalizer(lang=lang,**constructor)
                if not replay:
                    references[key] = reference if not constructor else Reference(lang=lang,deterministic=lang!='ru',
                        cache_dir=None if lang=='rw' else str(ROOT/'.cache/nemo'/lang),
                        **({'input_case':'cased'} | constructor))
            expected = row['reference'] if replay else call(references[key], row, timeout)
            actual = call(models[key], row, timeout)
            outcome = status(expected, actual)
            counters[outcome] += 1
            result = dict(row, reference=expected, actual=actual, status=outcome)
            if 'upstream_expected' in row:
                clean = (lambda s:s.strip()) if row.get('upstream_strip_expected') else (lambda s:s)
                expected_options = [clean(s) for s in row['upstream_expected']]
                result['upstream_expected_match'] = actual['error'] is None and clean(actual['output']) in expected_options
                result['reference_upstream_expected_match'] = expected['error'] is None and clean(expected['output']) in expected_options
            out.write(json.dumps(result, ensure_ascii=True)+'\n')
            out.flush()
    return lang, dict(counters)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--languages', nargs='+', choices=SUPPORTED_LANGUAGES, default=list(SUPPORTED_LANGUAGES))
    parser.add_argument('--upstream', type=Path, default=ROOT/'.cache/nemo-upstream')
    parser.add_argument('--seed', type=int, default=20260925)
    parser.add_argument('--count', type=int, default=500, help='Generated cases per language, in addition to upstream/edge cases')
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=15)
    parser.add_argument('--output', type=Path, default=ROOT/'.cache/stress-initial')
    parser.add_argument('--case-source', choices=['all', 'upstream', 'generated'], default='all')
    parser.add_argument('--replay', type=Path, help='Read recorded reference results instead of running NeMo')
    args = parser.parse_args()
    if args.replay and args.replay.resolve() == args.output.resolve():
        parser.error('Replay output must be different from source')
    args.output.mkdir(parents=True, exist_ok=True)
    tasks = []
    for lang in args.languages:
        rows = ([json.loads(line) for line in (args.replay/f'{lang}.jsonl').read_text().splitlines()]
                if args.replay else inputs(lang,args.upstream,args.seed,args.count))
        if args.case_source != 'all':
            rows = [r for r in rows if r['source'].startswith('upstream:') == (args.case_source == 'upstream')]
        tasks.append((lang, rows, args.output, args.timeout, bool(args.replay)))
    summary = {'seed': args.seed, 'upstream_commit': UPSTREAM_COMMIT, 'languages': {}, 'cases': 0,
               'counts': {}, 'input_sha256': hashlib.sha256(json.dumps([t[1] for t in tasks],ensure_ascii=True).encode()).hexdigest()}
    totals = Counter()
    with multiprocessing.get_context('spawn').Pool(args.jobs) as pool:
        for lang, counts in pool.imap_unordered(worker, tasks):
            summary['languages'][lang] = counts
            totals.update(counts)
            summary['counts'] = dict(totals)
            summary['cases'] = sum(totals.values())
            (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            print(lang, counts, flush=True)
    return int(any(totals[k] for k in ('mismatch','regression_error','timeout','reference_rejects_only')))

if __name__ == '__main__':
    sys.exit(main())
