"""Byte-level tropical weighted transducers, implemented with the standard library.

Graph data is immutable. A frontier decoder handles unambiguous rewrites; tied
outputs use a trimmed lattice and OpenFst-compatible topological ordering.
Weights are rounded to float32 at each addition, as in the source grammars.
No beam pruning or vocabulary approximations are used.
"""
from array import array
from collections import deque
import gzip
import math
import struct
import sys


class NoPathError(ValueError):
    """The grammar has no accepting path for this input."""


class Graph:
    def __init__(self, path):
        with gzip.open(path, 'rb') as source:
            magic, self.start, states, arcs = struct.unpack('<8sIII', source.read(20))
            if magic != b'KITTEN1\0':
                raise ValueError(f'Invalid grammar: {path}')
            for name, kind, size in [('offsets', 'I', states + 1), ('finals', 'f', states),
                                     ('labels', 'I', arcs), ('targets', 'I', arcs), ('weights', 'f', arcs)]:
                values = array(kind)
                values.frombytes(source.read(size * 4))
                if len(values) != size:
                    raise ValueError(f'Truncated grammar: {path}')
                if sys.byteorder != 'little':
                    values.byteswap()
                setattr(self, name, values)
        self._index = {}

    def arcs(self, state):
        index = self._index.get(state)
        if index is None:
            index = {}
            for i in range(self.offsets[state], self.offsets[state + 1]):
                label = self.labels[i]
                index.setdefault(label & 255, []).append((self.targets[i], self.weights[i],
                                                        bytes([label >> 8]) if label >> 8 else b''))
            # Bound auxiliary memory; graph arrays remain the source of truth.
            if len(self._index) >= 50000:
                self._index.clear()
            self._index[state] = index
        return index

    def rewrite(self, text):
        # Most inputs have one best output. Keep only the current input frontier
        # there; build a full lattice only when equal-cost output strings differ.
        # Pynini compiles NUL bytes as epsilon labels, so they consume no input.
        text = text.replace('\x00', '')
        active = {self.start: (0.0, b'', False)}
        pack, unpack = struct.Struct('<f').pack, struct.Struct('<f').unpack
        for char in (*text.encode('utf-8'), None):
            queue = deque(active)
            queued = set(active)
            while queue:
                state = queue.popleft()
                queued.discard(state)
                cost, output, ambiguous = active[state]
                for target, weight, suffix in self.arcs(state).get(0, ()):
                    candidate = unpack(pack(cost + weight))[0] if weight else cost
                    old = active.get(target)
                    value = output + suffix
                    if old is None or candidate < old[0]:
                        active[target] = (candidate, value, ambiguous)
                    elif candidate == old[0] and not old[2] and (ambiguous or value != old[1]):
                        active[target] = (old[0], old[1], True)
                    else:
                        continue
                    if target not in queued:
                        queue.append(target)
                        queued.add(target)
            if char is None:
                best = None
                for state, (cost, output, ambiguous) in active.items():
                    final = self.finals[state]
                    if not math.isfinite(final):
                        continue
                    candidate = unpack(pack(cost + final))[0]
                    if best is None or candidate < best[0]:
                        best = (candidate, output, ambiguous)
                    elif candidate == best[0] and (ambiguous or output != best[1]):
                        best = (best[0], best[1], True)
                if best is None:
                    raise NoPathError(f'No accepting path for {text[:80]!r}')
                if best[2]:
                    return self._rewrite_ordered(text)
                return best[1].decode('utf-8')
            following = {}
            for state, (cost, output, ambiguous) in active.items():
                for target, weight, suffix in self.arcs(state).get(char, ()):
                    candidate = unpack(pack(cost + weight))[0] if weight else cost
                    old = following.get(target)
                    value = output + suffix
                    if old is None or candidate < old[0]:
                        following[target] = (candidate, value, ambiguous)
                    elif candidate == old[0] and not old[2] and (ambiguous or value != old[1]):
                        following[target] = (old[0], old[1], True)
            if not following:
                raise NoPathError(f'No accepting path for {text[:80]!r}')
            active = following

    def _rewrite_ordered(self, text):
        data = text.encode('utf-8')
        length = len(data)
        start = (0, self.start)
        adjacency = {}

        def edges(node):
            position, state = node
            arcs = self.arcs(state)
            out = [((position, target), weight, suffix) for target, weight, suffix in arcs.get(0, ())]
            if position < length:
                out.extend(((position + 1, target), weight, suffix)
                           for target, weight, suffix in arcs.get(data[position], ()))
            adjacency[node] = out
            return out

        # Reverse DFS finishing order matches OpenFst's topological queue. In
        # particular, the order of equal-weight readings is not arbitrary.
        seen = {start}
        visiting = {start}
        stack = [(start, iter(edges(start)))]
        ordered = []
        while stack:
            node, iterator = stack[-1]
            edge = next(iterator, None)
            if edge is None:
                ordered.append(node)
                visiting.remove(node)
                stack.pop()
                continue
            target = edge[0]
            if target not in seen:
                seen.add(target)
                visiting.add(target)
                stack.append((target, iter(edges(target))))
        # Composition in OpenFst trims states that cannot reach a final state.
        # Some grammars contain dead epsilon cycles, so trim before decoding.
        reverse = {}
        live = set()
        for node, outgoing in adjacency.items():
            if node[0] == length and math.isfinite(self.finals[node[1]]):
                live.add(node)
            for target, _, _ in outgoing:
                reverse.setdefault(target, []).append(node)
        pending = list(live)
        while pending:
            for parent in reverse.get(pending.pop(), ()):
                if parent not in live:
                    live.add(parent)
                    pending.append(parent)
        if start not in live:
            raise NoPathError(f'No accepting path for {text[:80]!r}')
        del reverse
        costs = {start: 0.0}
        parents = {}
        best, final = float('inf'), None
        pack, unpack = struct.Struct('<f').pack, struct.Struct('<f').unpack
        pending = deque(node for node in reversed(ordered) if node in live)
        queued = set(pending)
        while pending:
            node = pending.popleft()
            queued.remove(node)
            cost = costs.get(node, float('inf'))
            if not math.isfinite(cost):
                continue
            position, state = node
            if position == length:
                candidate = unpack(pack(cost + self.finals[state]))[0]
                if candidate < best:
                    best, final = candidate, node
            for target, weight, suffix in adjacency[node]:
                if target not in live:
                    continue
                candidate = unpack(pack(cost + weight))[0] if weight else cost
                if candidate < costs.get(target, float('inf')):
                    costs[target] = candidate
                    parents[target] = (node, suffix)
                    # Usually the lattice is a DAG. Requeue an already visited
                    # state if a live epsilon cycle improves its distance.
                    if target not in queued:
                        pending.append(target)
                        queued.add(target)
        if final is None:
            raise NoPathError(f'No accepting path for {text[:80]!r}')
        result = []
        while final != start:
            final, suffix = parents[final]
            result.append(suffix)
        return b''.join(reversed(result)).decode('utf-8')
