import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from kitten_text_processing import Normalizer, PRESERVES_SENTINELS, SUPPORTED_LANGUAGES, normalize_text, warm

ROOT = Path(__file__).resolve().parents[1]


class APITests(unittest.TestCase):
    def test_kitten_interface(self):
        warm()
        self.assertTrue(PRESERVES_SENTINELS)
        self.assertEqual(normalize_text('I paid $12.50 for 3 books.'),
                         'I paid twelve dollars fifty cents for three books.')
        for value in (None, '', '  ', 0):
            self.assertEqual(normalize_text(value), value)
        self.assertEqual(normalize_text(42), 'forty two')
        with self.assertRaises(NotImplementedError):
            normalize_text('Hello', return_spans=True)

    def test_locale_is_not_stuck_on_first_language(self):
        self.assertEqual(normalize_text('2', locale='en-US'), 'two')
        self.assertEqual(normalize_text('2', locale='es_ES'), 'dos')
        self.assertEqual(normalize_text('2', locale='en-GB'), 'two')
        with self.assertRaises(ValueError):
            normalize_text('2', locale='xx-XX')
        with self.assertRaises(ValueError):
            warm('xx')
        with self.assertRaises(ValueError):
            Normalizer(input_case='lower_cased')

    def test_punctuation_options_and_unicode(self):
        n = Normalizer()
        self.assertEqual(n.normalize('  '), '')
        with self.assertRaises(TypeError):
            n.normalize(None)
        self.assertEqual(n.normalize('Hello, world!', punct_post_process=True), 'Hello, world!')
        self.assertEqual(n.normalize_list(['2', '3']), ['two', 'three'])
        self.assertIn('\ue0000\ue001', normalize_text('Keep \ue0000\ue001 and 12 books.'))
        self.assertIn('café', normalize_text('The café sells 2 cakes.'))

    def test_equivalent_lower_cased_grammars(self):
        for lang in ('ko', 'hy'):
            self.assertEqual(Normalizer(lang=lang, input_case='lower_cased').normalize('12'),
                             Normalizer(lang=lang).normalize('12'))

    def test_concurrent_shared_instance(self):
        n = Normalizer()
        inputs = ['I have 2 cats.', 'She paid $3.50.', 'Meet at 10:30.', 'Read [4].'] * 8
        expected = [n.normalize(s, punct_post_process=True) for s in inputs]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            actual = list(pool.map(lambda s: n.normalize(s, punct_post_process=True), inputs))
        self.assertEqual(actual, expected)

    def test_bundled_data_integrity(self):
        for lang in SUPPORTED_LANGUAGES:
            folder = ROOT / 'kitten_text_processing/data' / lang
            metadata = json.loads((folder / 'metadata.json').read_text())
            self.assertEqual(metadata['language'], lang)
            for name, values in metadata['graphs'].items():
                data = (folder / f'{name}.fst.gz').read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), values['sha256'])

    def test_runs_without_site_packages(self):
        # -S disables all site-packages, including any accidentally installed oracle.
        completed = subprocess.run([sys.executable, '-S', '-m', 'kitten_text_processing',
                                    '--lang', 'es', 'Tengo 2 gatos.'], cwd=ROOT,
                                   capture_output=True, text=True, check=True)
        self.assertEqual(completed.stdout.strip(), 'Tengo dos gatos.')


if __name__ == '__main__':
    unittest.main()
