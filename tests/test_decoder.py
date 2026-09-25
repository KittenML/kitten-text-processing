"""Small independent transducers exercise the decoder, not corpus memorization."""
from array import array
import unittest

from kitten_text_processing._fst import Graph, NoPathError


def graph(edges, finals):
    states = max([*finals, *(s for s, _, _, _, _ in edges), *(t for _, t, _, _, _ in edges)]) + 1
    g = Graph.__new__(Graph)
    g.start, g._index = 0, {}
    g.offsets, g.labels, g.targets, g.weights = (array(c) for c in ('I', 'I', 'I', 'f'))
    g.finals = array('f', (finals.get(s, float('inf')) for s in range(states)))
    for state in range(states):
        g.offsets.append(len(g.labels))
        for source, target, ilabel, olabel, weight in edges:
            if source == state:
                g.labels.append(ilabel | (olabel << 8))
                g.targets.append(target)
                g.weights.append(weight)
    g.offsets.append(len(g.labels))
    return g


class DecoderTests(unittest.TestCase):
    pass


def case_test(case):
    def test(self):
        g=graph(case['edges'],{int(k):v for k,v in case['finals'].items()})
        g.project_output=case.get('project_output',False)
        for check in case['checks']:
            with self.subTest(input=check['input']):
                if check.get('error'):
                    with self.assertRaises(NoPathError): g.rewrite(check['input'])
                else:
                    self.assertEqual(g.rewrite(check['input']),check['expected'])
    return test


import json
from pathlib import Path
for _case in json.loads((Path(__file__).parent/'decoder_cases.json').read_text()):
    setattr(DecoderTests,'test_'+_case['name'],case_test(_case))

if __name__ == '__main__':
    unittest.main()
