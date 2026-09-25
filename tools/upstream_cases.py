"""Read all vendored TN fixtures, retaining their original expectations and settings."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cases(lang):
    base = ROOT/'tests/upstream'
    manifest = json.loads((base/'manifest.json').read_text())
    for path in sorted((base/lang).glob('*.txt')):
        key = f'{lang}/{path.name}'
        setting = manifest['settings'].get(key, {'options': {'punct_post_process': False}, 'audio_only': False})
        # The English n-best fixture is block-formatted, rather than tilde-separated pairs.
        if 'normalize_with_audio' in path.name:
            text, expected, lineno = None, [], 0
            blocks = []
            for i, line in enumerate(path.read_text().split('\n'), 1):
                if line.startswith('~'):
                    if text is not None: blocks.append((lineno, text, expected))
                    text, expected, lineno = line.strip().replace('~',''), [], i
                elif text is not None and line:
                    expected.append(line.strip())
            if text is not None: blocks.append((lineno, text, expected))
        else:
            blocks=[]
            for i,line in enumerate(path.read_text().split('\n'),1):
                if not line: continue
                parts=line.split('~')
                if len(parts)<2: raise ValueError(f'Malformed upstream fixture: {key}:{i}')
                text, expected = (parts[1], [parts[0]]) if setting.get('input_column', 0)==1 else (parts[0],parts[1:])
                blocks.append((i,text,expected))
        for lineno,text,expected in blocks:
            yield {'id':f'upstream:{key}:{lineno}', 'lang':lang, 'input':text,
                   'source':f'upstream:{key}:{lineno}', 'options':setting['options'],
                   'constructor_options':setting.get('constructor_options',{}),
                   'upstream_strip_expected':setting.get('strip_expected',False),
                   'upstream_expected':expected, 'upstream_audio_only':setting['audio_only'] or lang=='ru'}
