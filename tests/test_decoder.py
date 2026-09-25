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
    def test_negative_edge_without_negative_cycle(self):
        g = graph([(0, 1, 97, 120, 1), (0, 2, 0, 0, 3), (2, 3, 97, 121, -5)], {1: 0, 3: 0})
        self.assertEqual(g.rewrite('a'), 'y')

    def test_equal_weight_ordering(self):
        g = graph([(0, 1, 97, 120, 0), (0, 2, 97, 121, 0)], {1: 0, 2: 0})
        self.assertEqual(g.rewrite('a'), 'y')

    def test_dead_epsilon_cycle_is_trimmed(self):
        g = graph([(0, 1, 0, 0, 0), (1, 0, 0, 0, 1),
                   (0, 2, 97, 120, 0), (0, 3, 97, 121, 0),
                   (0, 4, 0, 0, 0), (4, 5, 0, 0, 0), (5, 4, 0, 0, 0)], {2: 0, 3: 0})
        self.assertEqual(g.rewrite('a'), 'y')

    def test_float32_rounding_at_each_addition(self):
        g = graph([(0, 1, 0, 0, 100_000_000), (1, 2, 97, 120, 1),
                   (1, 3, 97, 121, 2)], {2: 0, 3: 0})
        # Both costs round to 100,000,000 in float32; traversal resolves the tie.
        self.assertEqual(g.rewrite('a'), 'y')

    def test_chain_contraction_keeps_join_predecessors(self):
        # Collapsing both branches into parallel arcs would select x instead of y.
        g = graph([(0, 1, 97, 0, 0), (0, 3, 97, 0, 0),
                   (1, 2, 0, 120, 0), (2, 5, 0, 0, 0),
                   (3, 4, 0, 121, 0), (4, 5, 0, 0, 0)], {5: 0})
        self.assertEqual(g.rewrite('a'), 'y')

    def test_final_weights_and_no_path(self):
        g = graph([(0, 1, 97, 120, 0), (0, 2, 97, 121, 0)], {1: 0, 2: 10})
        self.assertEqual(g.rewrite('a'), 'x')
        with self.assertRaises(NoPathError):
            g.rewrite('b')

    def test_utf8_byte_labels(self):
        g = graph([(0, 1, 0xC3, 0xC3, 0), (1, 2, 0xA9, 0xA9, 0)], {2: 0})
        self.assertEqual(g.rewrite('é'), 'é')


if __name__ == '__main__':
    unittest.main()
