"""Side-by-side warm-call timing; no repeated-output memoization is used.

Requires the development oracle environment. All engines receive the same
sentences in rotating order; outputs are checked on every measured call.
"""
import argparse
import importlib.util
import json
import logging
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter, process_time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import kitten_text_processing.normalizer as module
from kitten_text_processing import SUPPORTED_LANGUAGES
from nemo_text_processing.text_normalization.normalize import Normalizer as Reference


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--languages',nargs='+',choices=SUPPORTED_LANGUAGES,default=list(SUPPORTED_LANGUAGES))
    parser.add_argument('--samples',type=int,default=20)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--output',type=Path,default=ROOT/'benchmarks/speed.json')
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    logging.disable(logging.CRITICAL)
    spec=importlib.util.spec_from_file_location('before_decoder',ROOT/'tools/baseline_fst.py')
    before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
    before.NoPathError=module.NoPathError
    class BeforeGraph(before.Graph):
        def __init__(self,path,**kwargs): super().__init__(path)
    engines=['before','optimized','nemo']
    report={'python':platform.python_version(),'platform':platform.platform(),'repeats':args.repeats,
            'method':'same inputs, rotating execution order, no output caching, warm calls; grammar construction excluded',
            'languages':{},'results':[]}
    for lang in args.languages:
        rows=[r for r in json.loads((ROOT/f'tests/corpus/{lang}.reference.json').read_text())['cases'] if r['reference_error'] is None]
        n=min(args.samples,len(rows))
        rows=[rows[round(i*(len(rows)-1)/max(n-1,1))] for i in range(n)]
        new_graph=module.Graph
        load={}
        models={}
        for name in engines:
            t=perf_counter()
            if name=='before':
                module.Graph=BeforeGraph
                try: models[name]=module.Normalizer(lang=lang)
                finally: module.Graph=new_graph
            elif name=='optimized': models[name]=module.Normalizer(lang=lang)
            else: models[name]=Reference(input_case='cased',lang=lang,deterministic=lang!='ru',cache_dir=None if lang=='rw' else str(ROOT/'.cache/nemo'/lang))
            load[name]=perf_counter()-t
        # Populate decoder arc indexes for these inputs. No normalized outputs are cached.
        for row in rows:
            for name in engines:
                actual=models[name].normalize(row['input'],punct_post_process=True)
                if actual!=row['expected']: raise AssertionError((lang,name,row['input'],actual,row['expected']))
        measured=[]
        for i,row in enumerate(rows):
            times={name:[] for name in engines};cpu={name:[] for name in engines}
            for repeat in range(args.repeats):
                order=engines[(i+repeat)%3:]+engines[:(i+repeat)%3]
                for name in order:
                    start=perf_counter();start_cpu=process_time()
                    actual=models[name].normalize(row['input'],punct_post_process=True)
                    cpu[name].append((process_time()-start_cpu)*1000)
                    times[name].append((perf_counter()-start)*1000)
                    if actual!=row['expected']: raise AssertionError((lang,name,row['input']))
            measured.append({'id':row['id'],'lang':lang,'input':row['input'],
                             'median_ms':{k:statistics.median(v) for k,v in times.items()},
                             'median_cpu_ms':{k:statistics.median(v) for k,v in cpu.items()}})
        medians={name:statistics.median(r['median_ms'][name] for r in measured) for name in engines}
        summary={'sentences':len(rows),'grammar_load_seconds':load,'median_ms':medians,
                 'speedup_vs_before':medians['before']/medians['optimized'],
                 'ratio_to_nemo':medians['optimized']/medians['nemo']}
        report['languages'][lang]=summary;report['results'].extend(measured)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(lang,summary,flush=True)
    return 0

if __name__=='__main__':sys.exit(main())
