# Upstream fixture provenance and scope

These 175 files are unchanged copies of **all `.txt` files in each of the 17
languages' `data_text_normalization` directories** at NVIDIA NeMo Text Processing
r1.2.0, commit `7efa127d968c081793ebf11fa94dfb4257302d48` (Apache-2.0).
`manifest.json` records SHA-256 hashes and settings extracted from upstream test
functions. Regenerate with `python tools/import_upstream_tests.py PATH_TO_CHECKOUT`.

There are 5,407 input records. Frozen references in `../extended` come from real
NeMo calls, including per-fixture punctuation flags, Hindi `post_process=False`,
and the equivalent Korean/Armenian `lower_cased` graphs. German and Russian
fixtures have reversed input/expected columns. Original expectations are also
retained, not overwritten by recorded outputs.

The scope is the single-output written-to-spoken Normalizer.
All fixture inputs are exercised, including 336 from audio/n-best tests, but this
does **not** implement or validate audio rescoring, n-best enumeration, inverse
normalization, or every upstream Python test/API. The Armenian whitelist fixture
is included even though its upstream test mistakenly references the time fixture.

Eighteen non-audio fixture expectations disagree with the pinned NeMo runtime:
four Italian URL punctuation spacings and fourteen Armenian whitelist nonbreaking
spaces. Both engines agree on these outputs. The original files remain untouched;
`../extended/manifest.json` records every discrepancy. Regression tests assert
compatibility with NeMo, not that these upstream expectation problems are fixed.
