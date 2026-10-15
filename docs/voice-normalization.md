# Voice-selected speech normalization

`VoiceNormalizer` is an optional C++ backend for the 16 Kitten TTS 2 voice
languages. The existing `Normalizer` and `normalize_text` NeMo compatibility
interfaces retain their existing behavior and dependency-free implementation.

The caller supplies the selected voice's language. Digits follow that language
even in mixed text: Hindi `12` becomes `बारह`, English `12` becomes `twelve`.
Written words retain their spelling. There is no text language detection or
public locale, date-order, calendar or pronunciation override.

| Language | Fixed profile | Number example |
|---|---|---|
| English | en-US | 1,234.56 |
| Arabic | ar-SA, Gregorian | ١٬٢٣٤٫٥٦ |
| Chinese | zh-CN | 1,234.56 |
| Dutch | nl-NL | 1.234,56 |
| French | fr-FR | 1 234,56 |
| German | de-DE | 1.234,56 |
| Hindi | hi-IN | 12,34,567.89 |
| Indonesian | id-ID | 1.234,56 |
| Italian | it-IT | 1.234,56 |
| Japanese | ja-JP | 1,234.56 |
| Korean | ko-KR | 1,234.56 |
| Polish | pl-PL | 1 234,56 |
| Portuguese | pt-BR | 1.234,56 |
| Russian | ru-RU | 1 234,56 |
| Spanish | es-ES | 1.234,56 |
| Turkish | tr-TR | 1.234,56 |

## Recognition and wording

* ASCII, Arabic-Indic, Persian, Devanagari and full-width decimal digits use
  the same value parser. Output is words, rather than reformatted digits.
* With both dot and comma, the last separator is the decimal separator and
  the other must form valid grouping. With one separator, the profile's
  decimal separator takes precedence; valid grouping is otherwise accepted.
  Spaces, nonbreaking spaces and apostrophes can identify grouped integers.
  Invalid punctuation/grouping is retained. An ungrouped list of integers
  separated by spaces is read as individual numbers.
* Decimal fractions are spoken digit by digit, including trailing zeros.
  Signs are explicit. Leading-zero integers, explicit PIN/code/phone contexts
  and telephone-shaped sequences use digit readings. Very large integers
  exceeding 15 digits also use digit readings.
* Four-digit year-first dates use YMD. Four-digit year-last numeric dates use
  MDY in English and DMY in the other profiles. For example, `05/01/2027`
  means May 1 in English and January 5 in Hindi. Named months identify the
  month. Gregorian leap-day validation happens before any date is rewritten.
  Two-digit years and dates without a year do not acquire an inferred century
  or current year. Invalid dates are preserved as complete spans.
* Currency codes identify the denomination. `$`, `€`, `£`, `₹`, `R$`, `₽`,
  `₩` and `₺` default to USD, EUR, GBP, INR, BRL, RUB, KRW and TRY. `¥`/`￥`
  mean CNY for Chinese and JPY for the other voice profiles. Explicit USD,
  EUR, GBP, INR, BRL, RUB, KRW, JPY, CNY, TRY, PLN, CHF, SAR, AED, OMR, KWD,
  BHD, CAD, AUD and IDR codes are supported.
* Amounts use native currency names and plural forms. Exact fractional
  amounts use supported minor units where applicable. Fractions exceeding
  a currency's usual minor-unit precision, and fractional amounts of
  zero-decimal currencies, are spoken as decimals in major units. Nothing is
  rounded or calculated with floating point. Explicit magnitude suffixes such
  as `$1.2M` and `₹1.25 लाख` are expanded by shifting decimal strings.
* Clock times support `HH:MM`, `HH:MM:SS`, and AM/PM. AM/PM is retained as
  spoken letters in English and converted to the corresponding 24-hour
  value for the other profiles. Dotted times require a clock cue; a bare
  `14.05` remains a number. Invalid clock values are retained. UTC/GMT offsets
  retain their sign and validate the offset before expansion.
* Dash ranges between numbers, amounts and clock times use a native range
  connector. Recognizable telephone numbers take precedence over numeric
  ranges. Percentage symbols before or after a value use native wording.
* URLs, email addresses, paths, alphanumeric identifiers, explicit software
  versions, IP-like strings and bare fractions are protected. Normalization
  does not guess a mathematical meaning for these identifiers.
* Chinese counters distinguish `两` where appropriate; Korean count counters
  use native attributive numbers. Dates and clocks have language-specific
  wording. These fixed rules do not implement general grammatical case
  inference from arbitrary surrounding prose.

## Serving and build

Rule data is frozen from ICU 78.2 / CLDR 48 and distributed with its Unicode
license. ICU 72 or newer executes those frozen rules; it does not select
whatever linguistic data happen to be installed on the serving machine.
`tools/export_voice_data.py` produces the shared C++ table from the checked-in
data and lexical glue. Both serving engines vendor the same source bytes.

```sh
cmake -S . -B build/voice -DKITTEN_BUILD_VOICE_NORMALIZATION=ON
cmake --build build/voice -j4
KITTEN_VOICE_NORMALIZATION_LIBRARY=$PWD/build/voice/libkitten_voice_normalization.so \
  python -m unittest discover -s tests -p test_voice.py -v
```

`tools/build_voice.sh` is a smaller shared-library-only build. Its optional
`ICU_CFLAGS` and `ICU_LIBS` inputs support a prepared compiler toolchain.
Python loads the library through `ctypes`, releasing the GIL during C++ calls.
The C++ API is thread safe and keeps four warmed formatters per language and
a bounded 4,096-entry cache. Serving never downloads data or compiles rules.

`prepare_for_segmentation` performs recognition without word rendering and
temporarily masks whitespace inside typed values. The caller restores the
internal U+FFFF markers before normalizing each planned segment. Input that
already contains that marker is left untouched by this planning helper.
This prevents a chunk boundary from separating `USD` from its amount or a
month name from its day/year. Heavy rendering stays per segment, so later
text can be processed after first audio.

`tools/audit_voice.py` replays local fixtures and records new outputs beside
their historical expectations. A different result from a legacy NeMo oracle
is a policy difference to review, not automatically a linguistic error or a
new golden answer. The legacy compatibility suites remain separate.
