"""Inputs that exposed real differences during upstream and adversarial testing."""
import json
from pathlib import Path
import unittest

from kitten_text_processing import Normalizer


class RegressionTests(unittest.TestCase):
    def test_previously_failing_inputs(self):
        rows=json.loads((Path(__file__).parent/'regressions.json').read_text())
        for lang in sorted({r['lang'] for r in rows}):
            normalizer=Normalizer(lang=lang)
            for row in rows:
                if row['lang'] != lang: continue
                with self.subTest(lang=lang,text=row['input'],options=row['options']):
                    self.assertEqual(normalizer.normalize(row['input'],**row['options']),row['expected'])

    def test_permutation_limit_raises_outside_verbalizer_fallback(self):
        # NeMo rejects an unsplittable token group, rather than returning raw text.
        normalizer=Normalizer(max_number_of_permutations_per_split=1)
        with self.assertRaises(ValueError):
            normalizer.normalize('January 5, 2026')

if __name__=='__main__':unittest.main()
