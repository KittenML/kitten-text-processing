"""Standalone multilingual written-to-spoken text normalization."""
from functools import lru_cache
import json
from pathlib import Path
import re
import threading

from ._detokenize import detokenize
from ._fst import Graph, NoPathError
from ._ordering import TokenOrdering
from ._punctuation import post_process_punct, pre_process
from ._token_parser import TokenParser

SUPPORTED_LANGUAGES = ('en', 'es', 'fr', 'de', 'pt', 'it', 'zh', 'ja', 'ko', 'hi', 'ar', 'ru', 'vi', 'hu', 'sv', 'hy', 'rw')
PRESERVES_SENTINELS = True
_LOCK = threading.RLock()


def language_code(locale):
    code = (locale or 'en-US').replace('_', '-').split('-')[0].lower()
    if code not in SUPPORTED_LANGUAGES:
        raise ValueError(f'Unsupported language {locale!r}; supported: {", ".join(SUPPORTED_LANGUAGES)}')
    return code


class Normalizer(TokenOrdering):
    """NeMo-compatible cased normalizer backed by bundled byte transducers.

    Only written-to-spoken normalization is included, not inverse normalization,
    audio rescoring, or custom grammar compilation. Korean and Armenian also
    accept lower_cased: their upstream graphs are identical to the cased graphs.
    Russian uses the best-weight path through NeMo's non-deterministic grammar.
    Instances can be shared between threads; parser state is local to each call.
    """
    def __init__(self, input_case='cased', lang='en', *, post_process=True,
                 max_number_of_permutations_per_split=729):
        if max_number_of_permutations_per_split < 1:
            raise ValueError('max_number_of_permutations_per_split must be positive')
        self.lang = language_code(lang)
        self.input_case = input_case
        self.max_number_of_permutations_per_split = max_number_of_permutations_per_split
        folder = Path(__file__).parent / 'data' / self.lang
        metadata = json.loads((folder / 'metadata.json').read_text())
        if input_case not in metadata.get('input_cases', ['cased']):
            raise ValueError(f'Unsupported input_case={input_case!r} for {self.lang}')
        self.tagger = Graph(folder / 'tagger.fst.gz')
        self.verbalizer = Graph(folder / 'verbalizer.fst.gz')
        self.post_processor = (Graph(folder / 'post.fst.gz', project_output=True)
                               if post_process and 'post' in metadata['graphs'] else None)

    def normalize(self, text, verbose=False, punct_pre_process=False, punct_post_process=False):
        if not isinstance(text, str):
            raise TypeError('text must be a string')
        original = text
        text = (pre_process(text) if punct_pre_process else text).strip()
        if not text:
            return text
        tagged = self.tagger.rewrite(text)
        if verbose:
            print(tagged)
        parser = TokenParser()
        parser(tagged)
        tokens = parser.parse()
        chunks = []
        groups = self._split_tokens_to_reduce_number_of_permutations(tokens)
        try:
            for group in groups:
                for candidate in self.generate_permutations(group):
                    try:
                        chunks.append(self.verbalizer.rewrite(candidate))
                        break
                    except NoPathError:
                        continue
                else:
                    return _escape(text)
        except ValueError:
            # NeMo returns its escaped input on malformed verbalizer tokens.
            return _escape(text)
        output = re.sub(' {2,}', ' ', ' '.join(chunks))
        if self.post_processor is not None and output.strip():
            output = self.post_processor.rewrite(output.strip())
        if punct_post_process:
            output = post_process_punct(original, detokenize(output, self.lang))
        return output

    def normalize_list(self, texts, **kwargs):
        return [self.normalize(text, **kwargs) for text in texts]


@lru_cache(maxsize=4)
def _get_normalizer(lang):
    return Normalizer(lang=lang)


def warm(locale='en-US'):
    """Load a language's grammar ahead of the first request (no downloads)."""
    with _LOCK:
        _get_normalizer(language_code(locale))


def normalize_text(text, locale='en-US', return_spans=False):
    """Normalize English or select another locale through the convenience API."""
    if return_spans:
        raise NotImplementedError('Grammar normalization does not provide character spans')
    lang = language_code(locale)
    if not (text and str(text).strip()):
        return text
    with _LOCK:
        normalizer = _get_normalizer(lang)
    return normalizer.normalize(str(text), punct_post_process=True).strip()


def _escape(text):
    return text.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
