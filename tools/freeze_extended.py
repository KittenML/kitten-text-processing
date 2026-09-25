"""Freeze verified oracle runs for dependency-free replay; refuse incomplete runs."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kitten_text_processing import SUPPORTED_LANGUAGES
from upstream_cases import cases


def main():
    upstream, generated = map(Path, sys.argv[1:3])
    for folder in (upstream, generated):
        summary=json.loads((folder/'summary.json').read_text())
        assert set(summary['languages']) == set(SUPPORTED_LANGUAGES), f'Incomplete run: {folder}'
        assert not (set(summary['counts']) - {'exact','both_reject'}), f'Failed run: {folder}'
    destination = ROOT/'tests/extended'
    destination.mkdir(exist_ok=True)
    report = {'oracle': 'nemo_text_processing==1.2.0, pynini==2.1.6.post1, sacremoses==0.2.0',
              'languages': {}, 'counts': {}, 'fixture_discrepancies': [], 'files': {}}
    report['upstream_commit']=json.loads((upstream/'summary.json').read_text())['upstream_commit']
    report['generated_seed']=json.loads((generated/'summary.json').read_text())['seed']
    totals = Counter()
    for lang in SUPPORTED_LANGUAGES:
        rows = [json.loads(line) for folder in (upstream, generated)
                for line in (folder/f'{lang}.jsonl').read_text().splitlines()]
        assert {r['id'] for r in rows if r['source'].startswith('upstream:')} == {r['id'] for r in cases(lang)}
        assert sum(not r['source'].startswith('upstream:') for r in rows) >= 1000
        assert all(r['status'] in ('exact','both_reject') for r in rows)
        assert all(not r['reference']['timeout'] and not r['actual']['timeout'] for r in rows)
        counts = Counter(r['status'] for r in rows)
        counts['upstream'] = sum(r['source'].startswith('upstream:') for r in rows)
        counts['audio_fixture_inputs'] = sum(r.get('upstream_audio_only', False) for r in rows)
        report['languages'][lang] = dict(counts)
        totals.update(counts)
        frozen=[]
        for row in rows:
            if row.get('reference_upstream_expected_match') is False and not row.get('upstream_audio_only'):
                report['fixture_discrepancies'].append({k: row[k] for k in ('id','input','upstream_expected','reference')})
            item = {k: v for k,v in row.items() if k not in ('actual','status','upstream_expected_match','reference_upstream_expected_match')}
            item['reference'] = {k: v for k,v in row['reference'].items() if k != 'seconds'}
            frozen.append(item)
        path=destination/f'{lang}.jsonl'
        path.write_text(''.join(json.dumps(r,ensure_ascii=True)+'\n' for r in frozen))
        report['files'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    report['counts'] = dict(totals)
    (destination/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['counts']))

if __name__=='__main__': main()
