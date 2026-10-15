"""Dependency-free multilingual text normalization for speech synthesis."""
from .normalizer import Normalizer, PRESERVES_SENTINELS, SUPPORTED_LANGUAGES, normalize_text, warm
from .voice import VoiceNormalizer, VOICE_LANGUAGES, VOICE_RULE_VERSION

__version__ = '0.2.0'
__all__ = ['Normalizer', 'PRESERVES_SENTINELS', 'SUPPORTED_LANGUAGES', 'normalize_text', 'warm']
__all__ += ['VoiceNormalizer', 'VOICE_LANGUAGES', 'VOICE_RULE_VERSION']
