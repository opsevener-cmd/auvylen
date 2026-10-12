# Scoring boundary

This remains an installable Python package, not an HTTP service. The API lists
engine metadata and fulfills paid development orders through the registry. There is no
standalone scoring execution endpoint. Keeping inference
code here allows a later worker or service to reuse it without frontend coupling.

`MockScoringEngine` hashes opaque fixture bytes and maps the result to a fake score.
Identical input produces identical numeric output; result timestamps record execution
time and therefore differ. Scores are synthetic and have no accuracy or aesthetic meaning.
There are no image parsers, model files, GPUs, datasets or external calls.

The mock's commercial flag applies only to this internal synthetic implementation.
Its production flag is false. All future execution must pass through the registry's
policy gate and preserve provenance; direct engine method calls are for unit tests.
