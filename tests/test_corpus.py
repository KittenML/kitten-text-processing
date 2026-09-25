"""All authored cases against actual frozen NeMo results, including failures."""
import json
from pathlib import Path
import unittest

from kitten_text_processing import Normalizer, SUPPORTED_LANGUAGES
from kitten_text_processing._fst import NoPathError

CORPUS = Path(__file__).parent / 'corpus'


class CorpusTests(unittest.TestCase):
    def test_inventory(self):
        paths = sorted(CORPUS.glob('*.txt'))
        self.assertEqual({p.stem for p in paths}, set(SUPPORTED_LANGUAGES))
        inputs = [(p.stem, line.split('|', 1)[1]) for p in paths for line in p.read_text().splitlines()]
        self.assertEqual(len(inputs), 1000)
        self.assertEqual(len(set(inputs)), 1000)


def language_test(lang):
    def test(self):
        normalizer = Normalizer(lang=lang)
        records = json.loads((CORPUS / f'{lang}.reference.json').read_text())['cases']
        raw = (CORPUS / f'{lang}.txt').read_text().splitlines()
        self.assertEqual(len(raw), len(records))
        for line, record in zip(raw, records):
            with self.subTest(case=record['id'], text=record['input']):
                category, text = line.split('|', 1)
                self.assertEqual(text, record['input'])
                self.assertEqual(category, record['category'])
                if record['reference_error'] is not None:
                    with self.assertRaises(NoPathError):
                        normalizer.normalize(text, punct_post_process=True)
                else:
                    self.assertEqual(normalizer.normalize(text, punct_post_process=True), record['expected'])
    return test


for _lang in SUPPORTED_LANGUAGES:
    setattr(CorpusTests, f'test_reference_{_lang}', language_test(_lang))

if __name__ == '__main__':
    unittest.main()
