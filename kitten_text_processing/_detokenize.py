"""Moses-compatible punctuation handling for the supported TN languages.

Reimplemented using only re and Unicode character properties. NeMo calls Moses
with a single string in a list, which is then split on whitespace.
"""
import re
from bisect import bisect_right
from ._unicode_data import ALPHA_RANGES, CURRENCY_SYMBOLS

_ALPHA_STARTS = tuple(a for a, _ in ALPHA_RANGES)

def _alpha(character):
    value = ord(character)
    i = bisect_right(_ALPHA_STARTS, value) - 1
    return i >= 0 and value <= ALPHA_RANGES[i][1]

_CJK = ((4352, 4607), (11904, 42191), (43072, 43135), (44032, 55215),
        (63744, 64255), (65072, 65103), (65381, 65500), (94208, 101119),
        (110592, 110895), (110960, 111359), (131072, 196607))


def _cjk(c):
    return any(a <= ord(c) <= b for a, b in _CJK)


def detokenize(text, lang):
    tokens = re.sub(r' @-@ ', '-', ' ' + text + ' ').split()
    quotes = {}
    space, result = ' ', ''
    for i, token in enumerate(tokens):
        if _cjk(token[0]) and lang != 'ko':
            result += ('' if i and _cjk(tokens[i-1][-1]) else space) + token
            space = ' '
        elif all(c in CURRENCY_SYMBOLS or c in '([{¿¡' for c in token):
            result += space + token
            space = ''
        elif re.fullmatch(r'[,\.?!:;\\%}\])]+', token):
            result += (' ' if lang == 'fr' and re.fullmatch(r'[?!:;\\%]', token) else '') + token
            space = ' '
        elif lang == 'en' and i and len(token) > 1 and token[0] == "'" and _alpha(token[1]):
            result += token
            space = ' '
        elif (lang in ('fr', 'it') and i+1 < len(tokens) and len(token) > 1
              and token[-1] == "'" and _alpha(token[-2]) and _alpha(tokens[i+1][0])):
            result += space + token
            space = ''
        elif re.fullmatch('[\'"„“`]+', token):
            key = '"' if all(c in '„“”' for c in token) else token
            count = quotes.get(key, 0)
            if count % 2 or (lang == 'en' and token == "'" and i and tokens[i-1].endswith('s')):
                result += token
                space = ' '
                if count % 2:
                    quotes[key] = count + 1
            else:
                result += space + token
                space = ''
                quotes[key] = count + 1
        else:
            result += space + token
            space = ' '
    return re.sub(' {2,}', ' ', result).strip()
