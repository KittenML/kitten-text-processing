"""Replay every upstream input and seeded edge case with no oracle installed."""
import hashlib
import json
from pathlib import Path
import unittest

from kitten_text_processing import Normalizer, SUPPORTED_LANGUAGES
from kitten_text_processing._fst import NoPathError
from tools.upstream_cases import cases

ROOT = Path(__file__).resolve().parents[1]


class ExtendedTests(unittest.TestCase):
    def test_complete_unchanged_upstream_inventory(self):
        manifest=json.loads((ROOT/'tests/upstream/manifest.json').read_text())
        self.assertEqual(len(manifest['files']), 175)
        for name,digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256((ROOT/'tests/upstream'/name).read_bytes()).hexdigest(),digest)
        report=json.loads((ROOT/'tests/extended/manifest.json').read_text())
        for lang in SUPPORTED_LANGUAGES:
            path=ROOT/'tests/extended'/f'{lang}.jsonl'
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),report['files'][path.name])
            rows=[json.loads(s) for s in path.read_text().splitlines()]
            actual=[r['id'] for r in rows if r['source'].startswith('upstream:')]
            self.assertCountEqual(actual,[r['id'] for r in cases(lang)])
            self.assertGreaterEqual(sum(not r['source'].startswith('upstream:') for r in rows),1000)


def language_test(lang):
    def test(self):
        models={}
        for line in (ROOT/'tests/extended'/f'{lang}.jsonl').read_text().splitlines():
            row=json.loads(line)
            constructor=row.get('constructor_options',{})
            key=json.dumps(constructor,sort_keys=True)
            if key not in models:
                models[key]=Normalizer(lang=lang,**constructor)
            with self.subTest(case=row['id']):
                expected=row['reference']
                self.assertFalse(expected['timeout'])
                if expected['error']:
                    error_type=expected['error'].split(':',1)[0]
                    exception={'FstOpError':NoPathError,'UnicodeEncodeError':UnicodeEncodeError}[error_type]
                    with self.assertRaises(exception):
                        models[key].normalize(row['input'],**row['options'])
                else:
                    self.assertEqual(models[key].normalize(row['input'],**row['options']),expected['output'])
    return test


for _lang in SUPPORTED_LANGUAGES:
    setattr(ExtendedTests,f'test_reference_{_lang}',language_test(_lang))
