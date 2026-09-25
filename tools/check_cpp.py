"""Run C++ and/or pure Python against the same frozen NeMo fixtures.

Only the Python standard library is used. No bindings, NeMo installation, or
network access is involved. Generated reports default to the ignored .cache/.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kitten_text_processing import Normalizer, SUPPORTED_LANGUAGES

ERRORS = {'FstOpError': 'NoPathError', 'UnicodeEncodeError': 'UnicodeError'}


def cases(lang, source='all'):
    if source in ('all', 'corpus'):
        for row in json.loads((ROOT/f'tests/corpus/{lang}.reference.json').read_text())['cases']:
            yield dict(id='corpus:'+row['id'], lang=lang, input=row['input'],
                       options={'punct_post_process': True}, constructor_options={},
                       expected=row['expected'], error=row['reference_error'])
    if source in ('all', 'extended'):
        for line in (ROOT/f'tests/extended/{lang}.jsonl').read_text().splitlines():
            row=json.loads(line)
            assert not row['reference']['timeout'], row['id']
            yield dict(row, expected=row['reference']['output'], error=row['reference']['error'])
    if source in ('all', 'regressions'):
        for i,row in enumerate(json.loads((ROOT/'tests/regressions.json').read_text())):
            if row['lang']==lang:
                yield dict(row,id=f'regression:{i}',constructor_options={},error=None)


def encode(row):
    constructor=row.get('constructor_options',{})
    options=row['options']
    fields=[row['lang'],constructor.get('input_case','cased'),str(int(constructor.get('post_process',True))),
            str(constructor.get('max_number_of_permutations_per_split',729)),
            str(int(options.get('punct_pre_process',False))),str(int(options.get('punct_post_process',False))),
            row['input'].encode('utf-8',errors='surrogatepass').hex()]
    return '\t'.join(fields)+'\n'


def run(args, lang):
    rows=list(cases(lang,args.source))
    if args.limit: rows=rows[:args.limit]
    outcomes={}
    times={}
    if args.backend in ('cpp','both'):
        start=time.perf_counter()
        process=subprocess.run([str(args.binary),'--data-dir',str(args.data),'--batch'],
            input=''.join(encode(row) for row in rows),text=True,capture_output=True,timeout=1200,check=True)
        result=[]
        for line in process.stdout.splitlines():
            parts=line.split('\t')
            if parts[0]=='OK' and len(parts)==2:
                result.append((bytes.fromhex(parts[1]).decode('utf-8'),None))
            elif parts[0]=='ERR' and len(parts)==3:
                result.append((None,parts[1]))
            else: raise AssertionError(f'Invalid C++ response: {line!r}')
        assert len(result)==len(rows), (lang,len(result),len(rows),process.stderr)
        outcomes['cpp']=result
        times['cpp_seconds']=time.perf_counter()-start
    if args.backend in ('python','both'):
        models={}
        result=[]
        start=time.perf_counter()
        for row in rows:
            constructor=row.get('constructor_options',{})
            key=json.dumps(constructor,sort_keys=True)
            if key not in models: models[key]=Normalizer(lang=lang,**constructor)
            try: result.append((models[key].normalize(row['input'],**row['options']),None))
            except Exception as error:
                name=type(error).__name__
                result.append((None,ERRORS.get(name,name)))
        outcomes['python']=result
        times['python_seconds']=time.perf_counter()-start
    counts={}
    failures=[]
    for backend,results in outcomes.items():
        counter=Counter()
        for row,(actual,error) in zip(rows,results):
            expected_error=row['error'].split(':',1)[0] if row['error'] else None
            expected_error=ERRORS.get(expected_error,expected_error)
            matched=error==expected_error and (error is not None or actual==row['expected'])
            counter['matching_rejection' if matched and error else 'exact' if matched else 'failed']+=1
            if not matched and len(failures)<50:
                failures.append(dict(backend=backend,id=row['id'],input=row['input'],expected=row['expected'],
                    expected_error=expected_error,actual=actual,error=error,options=row['options'],
                    constructor_options=row.get('constructor_options',{})))
        counts[backend]=dict(counter)
    return lang,dict(cases=len(rows),counts=counts,failures=failures,**times)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,default=ROOT/'build/cpp/kitten-normalize-cpp')
    parser.add_argument('--data',type=Path,default=ROOT/'build/cpp/data')
    parser.add_argument('--backend',choices=['cpp','python','both'],default='both')
    parser.add_argument('--languages',nargs='+',choices=SUPPORTED_LANGUAGES,default=list(SUPPORTED_LANGUAGES))
    parser.add_argument('--source',choices=['all','corpus','extended','regressions'],default='all')
    parser.add_argument('--limit',type=int,default=0)
    parser.add_argument('--jobs',type=int,default=3)
    parser.add_argument('--output',type=Path,default=ROOT/'.cache/cpp-validation.json')
    args=parser.parse_args()
    args.binary=args.binary.resolve(); args.data=args.data.resolve()
    report={'languages':{},'source':args.source,'backend':args.backend}
    failed=False
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures=[pool.submit(run,args,lang) for lang in args.languages]
        for future in as_completed(futures):
            lang,result=future.result()
            report['languages'][lang]=result
            failed |= any(c.get('failed',0) for c in result['counts'].values())
            args.output.write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n')
            print(lang,result['cases'],result['counts'],flush=True)
    print('PASS' if not failed else 'FAIL',sum(r['cases'] for r in report['languages'].values()),'shared cases',flush=True)
    return int(failed)


if __name__=='__main__': sys.exit(main())
