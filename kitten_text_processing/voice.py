"""Fixed, voice-selected speech normalization through the shared C++ backend.

The existing pure-Python NeMo compatibility API does not load this backend.
Build cpp/voice at deployment time; runtime never compiles or downloads data.
"""
import ctypes
import os
from pathlib import Path

VOICE_LANGUAGES = ('en','ar','zh','nl','fr','de','hi','id','it','ja','ko','pl','pt','ru','es','tr')
VOICE_RULE_VERSION = 'voice-20261015-1'

class VoiceNormalizer:
    def __init__(self, library=None):
        path = library or os.environ.get('KITTEN_VOICE_NORMALIZATION_LIBRARY')
        if not path:
            path = Path(__file__).parent / 'libkitten_voice_normalization.so'
        self._lib = ctypes.CDLL(str(path))
        self._lib.kitten_voice_normalize.argtypes = [ctypes.c_char_p, ctypes.c_longlong, ctypes.c_char_p,
                                                    ctypes.POINTER(ctypes.c_longlong)]
        self._lib.kitten_voice_normalize.restype = ctypes.c_void_p
        self._lib.kitten_voice_prepare.argtypes = self._lib.kitten_voice_normalize.argtypes
        self._lib.kitten_voice_prepare.restype = ctypes.c_void_p
        self._lib.kitten_voice_free.argtypes = [ctypes.c_void_p]
        self._lib.kitten_voice_warm.argtypes = []
        self._lib.kitten_voice_warm.restype = ctypes.c_int

    def warm(self):
        if self._lib.kitten_voice_warm() != 0:
            raise RuntimeError('Voice normalization data failed to load')

    def normalize(self, text, language='en'):
        return self._call(self._lib.kitten_voice_normalize, text, language)

    def prepare_for_segmentation(self, text, language='en'):
        return self._call(self._lib.kitten_voice_prepare, text, language)

    def _call(self, function, text, language):
        if not isinstance(text, str):
            raise TypeError('text must be a string')
        language = str(language).replace('_','-').split('-',1)[0].lower()
        if language not in VOICE_LANGUAGES:
            raise ValueError('Unsupported voice language')
        data = text.encode('utf-8')
        size = ctypes.c_longlong()
        ptr = function(data,len(data),language.encode('ascii'),ctypes.byref(size))
        if not ptr:
            raise RuntimeError('Voice normalization failed')
        try:
            return ctypes.string_at(ptr,size.value).decode('utf-8')
        finally:
            self._lib.kitten_voice_free(ptr)
