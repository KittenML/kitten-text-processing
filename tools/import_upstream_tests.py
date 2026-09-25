"""Vendor unchanged NeMo r1.2.0 text-normalization fixtures and test-call metadata."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kitten_text_processing import SUPPORTED_LANGUAGES
COMMIT = '7efa127d968c081793ebf11fa94dfb4257302d48'


def main():
    source = Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'.cache/nemo-upstream'
    actual = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if actual != COMMIT:
        raise RuntimeError(f'Expected {COMMIT}, got {actual}')
    output = ROOT/'tests/upstream'
    output.mkdir(parents=True,exist_ok=True)
    metadata = {'repository':'https://github.com/NVIDIA/NeMo-text-processing', 'commit':COMMIT,
                'license':'Apache-2.0', 'files':{}, 'settings':{}}
    for lang in SUPPORTED_LANGUAGES:
        base = source/'tests/nemo_text_processing'/lang
        for p in sorted((base/'data_text_normalization').glob('*.txt')):
            target = output/lang/p.name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target)
            metadata['files'][f'{lang}/{p.name}'] = hashlib.sha256(p.read_bytes()).hexdigest()
        for p in base.glob('test*.py'):
            tree=ast.parse(p.read_text())
            parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
            for node in ast.walk(tree):
                if not isinstance(node,ast.FunctionDef): continue
                refs=[]
                for deco in node.decorator_list:
                    for n in ast.walk(deco):
                        if isinstance(n,ast.Constant) and isinstance(n.value,str) and '/data_text_normalization/' in n.value:
                            refs.append(n.value.split('/')[-1])
                calls=[n for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                       and n.func.attr=='normalize']
                for name in refs:
                    if not calls: continue
                    call=calls[0]
                    options={kw.arg: ast.literal_eval(kw.value) for kw in call.keywords
                             if kw.arg in ('punct_pre_process','punct_post_process')}
                    options.setdefault('punct_post_process',False)
                    audio=any(kw.arg=='n_tagged' for kw in call.keywords)
                    constructor = {}
                    owner = parents.get(node)
                    while owner is not None and not isinstance(owner, ast.ClassDef):
                        owner = parents.get(owner)
                    field = call.func.value.attr if isinstance(call.func.value,ast.Attribute) else None
                    if owner is not None:
                        for assignment in owner.body:
                            if (isinstance(assignment,ast.Assign) and any(isinstance(t,ast.Name) and t.id==field for t in assignment.targets)
                                    and isinstance(assignment.value,ast.Call)):
                                constructor = {kw.arg:ast.literal_eval(kw.value) for kw in assignment.value.keywords
                                               if kw.arg in ('post_process','input_case')}
                    strip_expected = any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                                         and n.func.attr=='strip' and isinstance(n.func.value,ast.Name)
                                         and n.func.value.id=='expected' for n in ast.walk(node))
                    metadata['settings'][f'{lang}/{name}']={'options':options,'constructor_options':constructor,
                        'strip_expected':strip_expected,'audio_only':audio,
                        'input_column': 1 if len(node.args.args)>1 and node.args.args[1].arg=='expected' else 0,
                        'test':p.name+':'+node.name}
    (output/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('Imported',len(metadata['files']),'unchanged upstream fixture files')

if __name__=='__main__': main()
