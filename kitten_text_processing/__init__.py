"""Dependency-free multilingual text normalization for speech synthesis."""
from .normalizer import Normalizer, PRESERVES_SENTINELS, SUPPORTED_LANGUAGES, normalize_text, warm

__version__ = '0.1.0'
__all__ = ['Normalizer', 'PRESERVES_SENTINELS', 'SUPPORTED_LANGUAGES', 'normalize_text', 'warm']
