"""Numpy-free identifiers shared by the API and the ML modules.

The API imports these at startup; the numerical modules that define behaviour (and load
numpy/ONNX) are imported only where a request or job actually needs them.
"""

AESTHETIC_SLUG = "auvylen-aesthetic"
NATIVE_SLUG = "auvylen-native"
BASELINE_EXTRACTOR = "rgb-grid-texture-v1"
RATING_IMPLEMENTATION = "rating-ridge-v1"
MIN_RATED_IMAGES = 8
MIN_GROUPS = 5
