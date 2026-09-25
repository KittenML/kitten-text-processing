# Kitten Text Processing

A standalone multilingual written-to-spoken normalizer with **zero runtime
dependencies**. It uses Python's standard library to interpret bundled NeMo
1.2.0 grammar data. No NeMo, Pynini, OpenFst, models, network access, or grammar
compilation is needed when installing or running the library.

```sh
pip install kitten-text-processing
python -m kitten_text_processing --lang en 'I paid $12.50 for 3 books.'
```

```python
from kitten_text_processing import normalize_text, warm, Normalizer

warm()  # optional; load English ahead of the first call
normalize_text('I paid $12.50 for 3 books.')
# 'I paid twelve dollars fifty cents for three books.'
normalize_text('Tengo 2 gatos.', locale='es-ES')
# 'Tengo dos gatos.'

normalizer = Normalizer(input_case='cased', lang='ja')
normalizer.normalize('猫が2匹います。', punct_post_process=True)
```

Languages: `en es fr de pt it zh ja ko hi ar ru vi hu sv hy rw`.
Locale tags such as `en-US`, `pt-BR`, `zh-CN`, and `hi_IN` select the corresponding
language grammar; they do not select separate regional grammars. Python 3.10+.

## C++ library

A standalone C++17 library and CLI are also included. C++ applications can link
`KittenTextProcessing::normalizer` through CMake. It uses the same grammar data
and test corpus, with no third-party runtime dependencies. See the
[C++ build and integration guide](https://github.com/KittenML/kitten-text-processing/blob/main/cpp/README.md).

Python imports continue using pure Python. There are no bindings or native
extensions in the Python package in this version.

## Convenience API

`normalize_text(text, locale='en-US', return_spans=False)` normalizes text and
cleans up punctuation. `warm(locale='en-US')` preloads a language grammar.
`PRESERVES_SENTINELS` indicates that private-use expression markers are retained.

`return_spans=True` raises `NotImplementedError`. Empty values are preserved by
`normalize_text`; `Normalizer.normalize` requires a string. Unsupported languages
raise `ValueError`.

## Design and scope

The runtime is Python code plus about 14 MB of compressed, portable grammar
arrays. It runs weighted byte transducers over UTF-8, parses the classified
tokens, tries the upstream field-order permutations, then verbalizes and applies
punctuation cleanup. Grammars are loaded lazily per language. The convenience
API retains at most four normalizers; explicit instances let callers control
lifetime. Instances are safe to call concurrently. Normalize sentence-sized
chunks: ambiguous long inputs can build large intermediate lattices.

The cased written-to-spoken grammars from the pinned NeMo release are included.
Inverse normalization, audio rescoring, custom whitelists, grammar compilation,
and separate `lower_cased` grammar variants are outside this package's scope.
Korean and Armenian also accept `lower_cased`: their upstream graphs were verified
to be identical to their cased graphs.
Russian uses NeMo's non-deterministic grammar and chooses a minimum-weight
reading; this is not a context-sensitive grammatical disambiguator.

Upstream limitations remain visible. In particular, Portuguese and Kinyarwanda
can reject ordinary inputs; a no-path error is raised rather than silently
claiming successful normalization. Some upstream outputs leave digits intact or
choose linguistically awkward readings. Compatibility is not a claim of perfect
linguistic correctness for all inputs.

## Validation and reproduction

For development, clone the repository and install locally with `pip install .`.

The `tests/corpus` directory contains 1,000 manually authored input sentences
across all 17 supported languages and separately recorded NeMo outputs. This is
a regression corpus, not an untouched holdout or native-speaker quality audit.

```sh
# Standard-library-only checks and comparison with frozen reference outputs
python -m unittest discover -s tests -v
python tools/benchmark.py

# Build-time/reference tooling only (never runtime dependencies)
python -m venv .venv-reference
.venv-reference/bin/pip install -r tools/requirements-reference.txt
.venv-reference/bin/python tools/export_grammars.py
.venv-reference/bin/python tools/benchmark.py --record-reference
```

**Expanded comparison: 22,976 exact outputs and 1,435 matching rejections, with
zero mismatches across 24,411 cases.** Validation also includes the original 1,000 authored
sentences, every one of the 5,407 upstream fixture inputs, and over 1,000 additional
generated/edge cases per language. Accepted outputs must match exactly; matching
rejections are counted separately. There are 18 original fixture expectations that
NeMo itself disagrees with; these remain unchanged and are explicitly recorded.
Audio/n-best fixture inputs are included, but audio rescoring is outside our scope.
See [upstream provenance](https://github.com/KittenML/kitten-text-processing/blob/main/tests/upstream/README.md).

The optimized engine is **1.8–7.8× faster than the previous implementation** on our
warm-call benchmark. English improved from 65.7 to 23.8 ms per sentence (NeMo:
7.7 ms); speed relative to NeMo varies by language. Measurements use 20
sentences per language, three repetitions, warmed grammar indexes, and rotating
execution order. Run `tools/speed_benchmark.py` in the reference environment to
produce a local report. Generated benchmark results are excluded from Git.
Grammar metadata records state/arc counts, upstream version, settings, and SHA-256 hashes.
The exporter skips already exported languages; to rebuild one, remove its
`metadata.json` and pass `--languages en` (or another language).

To regenerate the expanded oracle suite (development dependencies required):

```sh
.venv-reference/bin/python tools/stress_test.py --case-source upstream --count 0 --output .cache/upstream-canonical
.venv-reference/bin/python tools/stress_test.py --case-source generated --seed 20261002 --count 1000 --output .cache/generated-canonical
python tools/freeze_extended.py .cache/upstream-canonical .cache/generated-canonical
.venv-reference/bin/python tools/speed_benchmark.py
```

The package and NeMo-derived grammar data use Apache-2.0. Frozen Sacremoses
Unicode tables use MIT. See `LICENSE`, `LICENSE-SACREMOSES`, and `NOTICE` for
provenance and retained notices.
