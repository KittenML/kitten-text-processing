# Expanded regression corpus

Each JSONL file contains all upstream text-normalization fixture inputs for its
language and more than 1,000 generated/edge cases. The generated cases are seeded
combinations, not manually written sentences; the original 1,000 manually written
sentences remain in `../corpus`.

The `reference` fields are captured from NeMo 1.2.0 with Pynini 2.1.6.post1 and
Sacremoses 0.2.0. Tests compare successful strings exactly, distinguish matching
no-path/Unicode failures, and never count timeouts as passes. Source IDs, constructor
settings, punctuation options, and original upstream expectations are retained.
No oracle dependency is needed to replay them. Hashes, counts, and fixture
expectation discrepancies are in `manifest.json`.

Regenerate using the commands in the root README. Runtime wheels contain neither
these examples nor any lookup table of sentence outputs.
