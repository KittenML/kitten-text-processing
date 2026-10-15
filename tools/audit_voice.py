"""Replay local JSONL/text fixtures without changing their historical oracles.

Outputs are diagnostic policy differences, not linguistic accuracy scores.
Run with --input PATH repeatedly; .txt inputs use --text-language (English).
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kitten_text_processing.voice import VoiceNormalizer, VOICE_LANGUAGES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--library')
    parser.add_argument('--text-language', default='en')
    args = parser.parse_args()
    normalizer = VoiceNormalizer(args.library)
    normalizer.warm()
    counts = Counter()
    languages = Counter()
    times = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w') as output:
        for path in args.input:
            # JSON permits literal U+2028/U+2029 inside strings; splitlines()
            # would split those valid fixture records in the middle.
            lines = path.read_text().split('\n')
            if lines and lines[-1] == '':
                lines.pop()  # file terminator, rather than another fixture
            for line_number, line in enumerate(lines, 1):
                if not line and path.suffix != '.txt':
                    continue
                if path.suffix == '.txt':
                    row = {'input': line, 'language': args.text_language}
                else:
                    row = json.loads(line)
                    if isinstance(row, str):
                        row = {'input': row, 'language': args.text_language}
                text = row.get('input', row.get('text', ''))
                lang = row.get('language_code', row.get('lang', row.get('language', args.text_language)))
                lang = str(lang).replace('_', '-').split('-')[0].lower()
                counts['total'] += 1
                result = {'source': str(path), 'line': line_number, 'language': lang,
                          'input': text, 'historical_expected': row.get('expected', row.get('after'))}
                if lang not in VOICE_LANGUAGES:
                    result['outcome'] = 'legacy_language_outside_voice_profiles'
                    counts['outside_profiles'] += 1
                else:
                    languages[lang] += 1
                    start = time.perf_counter()
                    try:
                        actual = normalizer.normalize(text, lang)
                        elapsed = (time.perf_counter() - start) * 1000
                        times.append(elapsed)
                        result.update(normalized=actual, milliseconds=elapsed, outcome='rendered')
                        counts['rendered'] += 1
                        counts['changed'] += actual != text
                        if normalizer.normalize(actual, lang) != actual:
                            result['outcome'] = 'not_idempotent'
                            counts['not_idempotent'] += 1
                        if not any(c.isdigit() for c in text) and actual != text:
                            counts['prose_changed'] += 1
                    except UnicodeError as exc:
                        result.update(outcome='invalid_unicode', error=type(exc).__name__)
                        counts['invalid_unicode'] += 1
                    except Exception as exc:
                        result.update(outcome='error', error=type(exc).__name__)
                        counts['errors'] += 1
                output.write(json.dumps(result, ensure_ascii=True) + '\n')
    times.sort()
    summary = {'counts': dict(counts), 'languages': dict(languages),
               'timings_ms': {f'p{q}': times[min(len(times)-1, int(len(times)*q/100))]
                              for q in (50, 95, 99)} if times else {},
               'interpretation': 'Historical NeMo outputs remain unchanged. This is a replay and policy-difference report, not an accuracy score.'}
    args.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    if counts['errors'] or counts['not_idempotent'] or counts['prose_changed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
