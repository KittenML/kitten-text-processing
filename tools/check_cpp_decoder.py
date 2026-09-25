"""Exercise both decoders on the same independent tiny graph fixtures."""
import argparse
import gzip
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kitten_text_processing._fst import Graph, NoPathError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    args=parser.parse_args()
    cases=json.loads((ROOT/'tests/decoder_cases.json').read_text())
    with tempfile.TemporaryDirectory() as directory:
        for case in cases:
            edges=case['edges']; finals={int(k):v for k,v in case['finals'].items()}
            states=max([*finals,*(e[0] for e in edges),*(e[1] for e in edges)])+1
            labels=[]; targets=[]; weights=[]; offsets=[]
            for s in range(states):
                offsets.append(len(labels))
                for source,target,ilabel,olabel,weight in edges:
                    if source==s:
                        labels.append(ilabel | olabel<<8);targets.append(target);weights.append(weight)
            offsets.append(len(labels))
            raw=struct.pack('<8sIII',b'KITTEN1\0',0,states,len(labels))
            for code,values in [('I',offsets),('f',[finals.get(i,float('inf')) for i in range(states)]),
                                ('I',labels),('I',targets),('f',weights)]:
                raw+=struct.pack('<'+code*len(values),*values)
            path=Path(directory)/'graph.fst';path.write_bytes(raw)
            zipped=path.with_suffix('.gz');zipped.write_bytes(gzip.compress(raw))
            projected=case.get('project_output',False)
            python=Graph(zipped,project_output=projected)
            for check in case['checks']:
                cpp=subprocess.run([str(args.binary),str(path),str(int(projected)),check['input']],capture_output=True)
                if check.get('error'):
                    assert cpp.returncode==2,(case['name'],cpp.stderr)
                    try: python.rewrite(check['input'])
                    except NoPathError: pass
                    else: raise AssertionError(case['name'])
                else:
                    assert cpp.returncode==0,(case['name'],cpp.stderr)
                    assert cpp.stdout.decode()==check['expected'],(case['name'],cpp.stdout)
                    assert python.rewrite(check['input'])==check['expected'],case['name']
        # Loader rejects truncated and inconsistent graph data instead of reading out of bounds.
        for malformed in (b'',raw[:18],raw[:-1],b'BADMAGIC'+raw[8:]):
            path.write_bytes(malformed)
            result=subprocess.run([str(args.binary),str(path),'0','a'],capture_output=True)
            assert result.returncode==1,result
    print(f'{len(cases)} shared decoder fixtures and malformed-data checks passed')


if __name__=='__main__':main()
