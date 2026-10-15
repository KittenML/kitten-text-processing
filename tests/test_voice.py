"""Independent policy examples for the optional voice-selected word renderer."""
import concurrent.futures
import os
import unittest

from kitten_text_processing.voice import VoiceNormalizer, VOICE_LANGUAGES


@unittest.skipUnless(os.environ.get('KITTEN_VOICE_NORMALIZATION_LIBRARY'), 'optional C++ voice backend')
class VoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n = VoiceNormalizer()
        cls.n.warm()

    def test_twelve_in_every_voice_language(self):
        words = dict(en='twelve', ar='اثنا عشر', zh='十二', nl='twaalf', fr='douze',
                     de='zwölf', hi='बारह', id='dua belas', it='dodici', ja='十二',
                     ko='십이', pl='dwanaście', pt='doze', ru='двенадцать',
                     es='doce', tr='on iki')
        for lang, expected in words.items():
            with self.subTest(lang=lang):
                self.assertEqual(self.n.normalize('12', lang), expected)

    def test_fixed_dates_and_invalid_values(self):
        self.assertEqual(self.n.normalize('05/01/2027', 'en'), 'May first, twenty twenty-seven')
        self.assertEqual(self.n.normalize('05/01/2027', 'hi'), 'पाँच जनवरी दो हज़ार सत्ताईस')
        self.assertEqual(self.n.normalize('2027-01-05', 'zh'), '二零二七年一月五日')
        self.assertEqual(self.n.normalize('5 January 2027', 'hi'), 'पाँच जनवरी दो हज़ार सत्ताईस')
        for lang in VOICE_LANGUAGES:
            for value in ('2027-02-29', '2027-13-05', '2027-01-32', '25:61', '14:99:05'):
                with self.subTest(lang=lang, value=value):
                    self.assertEqual(self.n.normalize(value, lang), value)

    def test_exact_precision_and_currency_spacing(self):
        self.assertEqual(self.n.normalize('₹12.50 है।', 'hi'), 'बारह रुपये और पचास पैसे है।')
        self.assertEqual(self.n.normalize('कीमत ₹12.50', 'hi'), 'कीमत बारह रुपये और पचास पैसे')
        self.assertEqual(self.n.normalize('USD12.50', 'en'), 'twelve US dollars and fifty cents')
        self.assertEqual(self.n.normalize('1.00', 'en'), 'one point zero zero')
        self.assertEqual(self.n.normalize('€0.001', 'en'), 'zero point zero zero one euros')
        self.assertEqual(self.n.normalize('12,50 €', 'es'), 'doce euros y cincuenta céntimos')
        self.assertEqual(self.n.normalize('Rp12.500,50', 'id'),
                         'dua belas ribu lima ratus koma lima nol Rupiah Indonesia')

    def test_identifiers_are_not_partially_rewritten(self):
        for lang in VOICE_LANGUAGES:
            for value in ('https://x.example/a?price=12.50', 'a12@example.com',
                          'v1.2.3', 'AB12.34', '192.168.1.2', '1e-10', '1/2'):
                with self.subTest(lang=lang, value=value):
                    self.assertEqual(self.n.normalize(value, lang), value)
        self.assertEqual(self.n.normalize('0012', 'en'), 'zero zero one two')
        self.assertEqual(self.n.normalize('PIN: 1234', 'en'), 'PIN: one two three four')

    def test_native_time_and_counters(self):
        self.assertEqual(self.n.normalize('1', 'de'), 'eins')
        self.assertEqual(self.n.normalize('21', 'it'), 'ventuno')
        self.assertEqual(self.n.normalize('21', 'es'), 'veintiuno')
        self.assertEqual(self.n.normalize('ट्रेन 14:05 बजे चलेगी।', 'hi'),
                         'ट्रेन चौदह बजकर पाँच मिनट पर चलेगी।')
        self.assertEqual(self.n.normalize('o 14:05', 'pl'), 'o czternastej zero pięć')
        self.assertEqual(self.n.normalize('12권', 'ko'), '열두 권')
        self.assertEqual(self.n.normalize('2个', 'zh'), '两个')

    def test_unicode_and_thread_safety(self):
        for value in ('१२', '١٢', '۱۲', '１２'):
            self.assertEqual(self.n.normalize(value, 'hi'), 'बारह')
        rows = [(str(i), lang) for lang in VOICE_LANGUAGES for i in range(1, 40)]
        expected = [self.n.normalize(text, lang) for text, lang in rows]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            actual = list(pool.map(lambda row: self.n.normalize(*row), rows))
        self.assertEqual(actual, expected)
        with self.assertRaises(ValueError):
            self.n.normalize('12', 'xx')

    def test_adjacent_values_ranges_and_magnitudes(self):
        self.assertEqual(self.n.normalize('9:30 PM 42 cents', 'en'), 'nine thirty p m forty-two cents')
        self.assertEqual(self.n.normalize('$1.2M', 'en'), 'one million two hundred thousand US dollars')
        self.assertEqual(self.n.normalize('₹1.25 लाख', 'hi'), 'एक लाख पच्चीस हज़ार रुपये')
        self.assertEqual(self.n.normalize('%12,5', 'tr'), 'yüzde on iki virgül beş')
        self.assertEqual(self.n.normalize('08:30-10:45', 'en'), 'eight thirty to ten forty-five')
        self.assertEqual(self.n.normalize('5-7 USD', 'en'), 'five US dollars to seven US dollars')
        self.assertEqual(self.n.normalize('1,,000', 'en'), '1,,000')
        self.assertEqual(self.n.normalize('02/03/04', 'en'), '02/03/04')
        self.assertEqual(self.n.normalize('1 2 3 4', 'en'), 'one two three four')

    def test_planning_masks_do_not_render_the_values(self):
        raw = 'Pay USD 1,234.56 on 5 January 2027 at 9:30 PM.'
        masked = self.n.prepare_for_segmentation(raw, 'en')
        self.assertIn('USD\uffff1,234.56', masked)
        self.assertIn('5\uffffJanuary\uffff2027', masked)
        self.assertEqual(masked.replace('\uffff', ' '), raw)
        self.assertEqual(self.n.prepare_for_segmentation('already\uffff 12', 'en'), 'already\uffff 12')


if __name__ == '__main__':
    unittest.main()
