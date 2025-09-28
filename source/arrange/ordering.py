# SPDX-License-Identifier: GPL-2.0-or-later

# https://link.springer.com/chapter/10.1007/3-540-36151-0_26
# https://doi.org/10.1016/j.jvlc.2013.11.005
# https://doi.org/10.1007/978-3-642-11805-0_14
# https://link.springer.com/chapter/10.1007/978-3-540-31843-9_22
# https://doi.org/10.7155/jgaa.00088

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable, Collection, Iterator, Sequence
from dataclasses import dataclass, field, replace
from functools import cache
from itertools import chain, pairwise
from math import inf
from operator import itemgetter
from statistics import fmean
from typing import TypeAlias, cast

import networkx as nx

from .. import config
from .graph import FROM_SOCKET, TO_SOCKET, Cluster, GNode, GType, Socket, socket_graph

# -------------------------------------------------------------------

_MixedGraph: TypeAlias = 'nx.DiGraph[GNode | Cluster]'


def get_col_nesting_trees(
  columns: Sequence[Collection[GNode]],
  T: _MixedGraph,
) -> list[_MixedGraph]:
    trees = []
    for col in columns:
        LT = nx.DiGraph()
        edges = nx.edge_bfs(T, col, orientation='reverse')
        LT.add_edges_from([e[:2] for e in edges])
        trees.append(LT)

    return trees


def expand_multi_inputs(G: nx.MultiDiGraph[GNode]) -> None:
    H = socket_graph(G)
    reroutes = {v for v in H if v.owner.is_reroute}
    for v in {s.owner for s in config.multi_input_sort_ids}:
        inputs = sorted({e[2] for e in G.in_edges(v, data=TO_SOCKET)}, key=lambda s: s.idx)
        i = inputs[0].idx
        for socket in inputs:
            if socket not in config.multi_input_sort_ids:
                if i != socket.idx:
                    d = next(d for *_, d in G.in_edges(v, data=True) if d[TO_SOCKET] == socket)
                    d[TO_SOCKET] = replace(socket, idx=i)
                i += 1
                continue

            sort_ids = config.multi_input_sort_ids[socket]
            SH = H.subgraph({i[0] for i in sort_ids} | {socket} | reroutes)
            seen = set()
            for base_from_socket in sorted(sort_ids, key=itemgetter(1), reverse=True):
                from_socket = next(
                  s for s, t in nx.edge_dfs(SH, base_from_socket) if t == socket and s not in seen)
                d = next(
                  d for d in G[from_socket.owner][v].values()
                  if d[TO_SOCKET] == socket and d[FROM_SOCKET] == from_socket)
                d[TO_SOCKET] = replace(socket, idx=i)
                seen.add(from_socket)
                i += 1


@cache
def reflexive_transitive_closure(LT: _MixedGraph) -> _MixedGraph:
    return cast(_MixedGraph, nx.transitive_closure(LT, reflexive=True))


@cache
def topologically_sorted_clusters(LT: _MixedGraph) -> list[Cluster]:
    return [h for h in nx.topological_sort(LT) if h.type == GType.CLUSTER]


@dataclass(slots=True)
class _ClusterCrossingsData:
    graph: nx.MultiDiGraph[GNode | Cluster]
    reduced_free_col: list[GNode | Cluster]
    fixed_col: list[GNode] = field(default_factory=list)
    expanded_fixed_col: list[GNode] = field(default_factory=list)

    border_pairs: dict[tuple[GNode, GNode], list[GNode]] = field(default_factory=dict)
    constrained_clusters: list[Cluster] = field(default_factory=list)

    fixed_sockets: dict[GNode, list[Socket]] = field(default_factory=dict)
    free_sockets: dict[GNode | Cluster, list[Socket]] = field(default_factory=dict)

    N: list[Socket] = field(default_factory=list)
    S: list[Socket] = field(default_factory=list)
    bipartite_edges: list[tuple[Socket, Socket, int]] = field(default_factory=list)


def crossing_reduction_graph(
  h: Cluster,
  LT: _MixedGraph,
  G: nx.MultiDiGraph[GNode],
) -> nx.MultiDiGraph[GNode | Cluster]:
    G_h = nx.MultiDiGraph()
    G_h.add_nodes_from(LT[h])
    TC = reflexive_transitive_closure(LT)
    for s, t, k, d in G.in_edges(TC[h], data=True, keys=True):  # type: ignore
        c = next(c for c in TC.pred[t] if c in LT[h])

        input_k = TO_SOCKET
        output_k = FROM_SOCKET
        if d[output_k].owner != s:
            input_k, output_k = output_k, input_k

        if (s, c, k) in G_h.edges and G_h.edges[s, c, k][output_k] == d[output_k]:
            G_h.edges[s, c, k]['weight'] += 1
            continue

        to_socket = d[input_k] if c.type != GType.CLUSTER else replace(d[input_k], owner=c, idx=0)
        G_h.add_edge(s, c, weight=1, from_socket=d[output_k], to_socket=to_socket)

    return G_h


_BALANCING_FAC = 1


def insert_border_edges(
  H: _ClusterCrossingsData,
  fixed_LT: _MixedGraph,
  free_LT: _MixedGraph,
  is_backwards: bool,
) -> None:
    free_clusters = {v for v in H.reduced_free_col if v.type == GType.CLUSTER}
    for c in free_clusters & fixed_LT.nodes:
        upper_v = GNode(type=GType.VERTICAL_BORDER)
        lower_v = GNode(type=GType.VERTICAL_BORDER)
        H.expanded_fixed_col.extend((upper_v, lower_v))

        fac = 1 + len((nx.descendants(free_LT, c) & fixed_LT.nodes))
        for border_v in upper_v, lower_v:
            H.graph.add_edge(
              border_v,
              c,
              weight=(0.5 * _BALANCING_FAC) * fac,
              from_socket=Socket(border_v, 0, not is_backwards),
              to_socket=Socket(c, 0, is_backwards),  # type: ignore
            )

        bordered_nodes = [v for v in nx.descendants(fixed_LT, c) if v.type != GType.CLUSTER]
        H.border_pairs[upper_v, lower_v] = bordered_nodes


def add_bipartite_edges(H: _ClusterCrossingsData) -> None:
    B = nx.DiGraph()
    edges = [(d[FROM_SOCKET], d[TO_SOCKET], d) for *_, d in H.graph.edges.data()]
    B.add_edges_from(edges)

    if B.edges:
        N, S = map(set, zip(*B.edges))
        if len(S) > len(N):
            N, S = S, N
            B = nx.reverse_view(B)

        H.N.extend(sorted(N, key=lambda d: d.idx))
        H.S.extend(sorted(S, key=lambda d: d.idx))

    H.bipartite_edges.extend(B.edges.data('weight'))


def crossing_reduction_data(
  G: nx.MultiDiGraph[GNode],
  trees: Sequence[_MixedGraph],
  is_backwards: bool = False,
) -> Iterator[list[_ClusterCrossingsData]]:
    pos = lambda v: v.col.index(v) if v.type != GType.CLUSTER else inf
    for i, free_LT in enumerate(trees[1:], 1):
        fixed_LT = trees[i - 1]
        fixed_col = next(v.col for v in fixed_LT if v.type != GType.CLUSTER)
        prev_clusters = {v for v in fixed_LT if v.type == GType.CLUSTER}
        data = []
        for h in topologically_sorted_clusters(free_LT):
            G_h = crossing_reduction_graph(h, free_LT, G)
            H = _ClusterCrossingsData(G_h, sorted(free_LT[h], key=pos))

            H.fixed_col = fixed_col
            H.expanded_fixed_col.extend(fixed_col)
            G_h.add_nodes_from(H.expanded_fixed_col)
            insert_border_edges(H, fixed_LT, free_LT, is_backwards)

            for u in H.expanded_fixed_col:
                if sockets := {e[2] for e in G_h.out_edges(u, data=FROM_SOCKET)}:
                    H.fixed_sockets[u] = sorted(
                      sockets, key=lambda d: d.idx, reverse=not is_backwards)

            for v in H.reduced_free_col:
                H.free_sockets[v] = [e[2] for e in G_h.in_edges(v, data=FROM_SOCKET)]

            H.constrained_clusters.extend([v for v in H.reduced_free_col if v in prev_clusters])
            add_bipartite_edges(H)

            data.append(H)

        yield data


# -------------------------------------------------------------------

_FreeColumns = list[tuple[list[GNode], _MixedGraph, list[_ClusterCrossingsData]]]


def sort_expanded_fixed_col(H: _ClusterCrossingsData) -> None:
    pos: dict[GNode, float] = {v: i for i, v in enumerate(H.fixed_col)}

    for (upper_v, lower_v), bordered_nodes in H.border_pairs.items():
        positions = [pos[v] for v in bordered_nodes]
        pos[upper_v] = min(positions) - 0.1
        pos[lower_v] = max(positions) + 0.1

    H.expanded_fixed_col.sort(key=pos.get)  # type: ignore


def calc_socket_ranks(H: _ClusterCrossingsData, is_forwards: bool) -> None:
    for v, sockets in H.fixed_sockets.items():
        incr = 1 / (len(sockets) + 1)
        rank = H.expanded_fixed_col.index(v) + 1
        if is_forwards:
            incr = -incr

        for socket in sockets:
            rank += incr
            v.cr.socket_ranks[socket] = rank


def calc_barycenters(H: _ClusterCrossingsData) -> None:
    for w in H.reduced_free_col:
        sockets = H.free_sockets[w]

        if not sockets:
            continue

        random_amount = random.uniform(-1, 1)
        w.cr.barycenter = (
          fmean([s.owner.cr.socket_ranks[s] for s in sockets]) +
          (random.uniform(0, 1) * random_amount - random_amount / 2))


def get_barycenter(v: GNode | Cluster) -> float:
    barycenter = v.cr.barycenter
    assert barycenter is not None
    return barycenter


def fill_in_unknown_barycenters(col: list[GNode | Cluster], is_first_iter: bool) -> None:
    if is_first_iter:
        max_b = max([b for v in col if (b := v.cr.barycenter) is not None], default=0) + 2
        for v in col:
            if v.cr.barycenter is None:
                v.cr.barycenter = random.uniform(0, 1) * max_b - 1
        return

    for i, v in enumerate(col):
        if v.cr.barycenter is not None:
            continue

        prev_b = get_barycenter(col[i - 1]) if i != 0 else 0
        next_b = next((b for w in col[i + 1:] if (b := w.cr.barycenter) is not None), prev_b + 1)
        v.cr.barycenter = (prev_b + next_b) / 2


def find_violated_constraint(GC: _MixedGraph) -> tuple[GNode | Cluster, GNode | Cluster] | None:
    active = [v for v in GC if GC[v] and not GC.pred[v]]
    incoming_constraints = defaultdict(list)
    while active:
        v = active.pop(0)

        for c in incoming_constraints[v]:
            if c[0].cr.barycenter >= v.cr.barycenter:
                return c

        for t in GC[v]:
            incoming_constraints[t].insert(0, (v, t))
            if len(incoming_constraints[t]) == GC.in_degree[t]:
                active.append(t)

    return None


def handle_constraints(H: _ClusterCrossingsData) -> None:

    # Optimization: don't pass constraints to `nx.DiGraph` constructor
    GC = nx.DiGraph()
    GC.add_edges_from(pairwise(H.constrained_clusters))

    unconstrained = set(H.reduced_free_col) - GC.nodes
    L = {v: [v] for v in H.reduced_free_col}

    deg = {v: H.graph.degree[v] for v in GC}
    while c := find_violated_constraint(GC):
        v_c = GNode(type=GType.DUMMY)
        s, t = c

        deg[v_c] = deg[s] + deg[t]
        assert s.cr.barycenter and t.cr.barycenter
        if deg[v_c] > 0:
            v_c.cr.barycenter = (s.cr.barycenter * deg[s] + t.cr.barycenter * deg[t]) / deg[v_c]
        else:
            v_c.cr.barycenter = (s.cr.barycenter + t.cr.barycenter) / 2

        L[v_c] = L[s] + L[t]

        nx.relabel_nodes(GC, {s: v_c, t: v_c}, copy=False)
        if (v_c, v_c) in GC.edges:
            GC.remove_edge(v_c, v_c)

        if v_c not in GC:
            unconstrained.add(v_c)

    groups = sorted(unconstrained | GC.nodes, key=get_barycenter)
    for i, v in enumerate(chain(*[L[v] for v in groups])):
        v.cr.barycenter = i


def get_cross_count(H: _ClusterCrossingsData) -> int:
    edges = H.bipartite_edges

    if not edges:
        return 0

    reduced_free_col = set(H.reduced_free_col)

    def pos(s: Socket) -> float:
        v = s.owner
        if v in reduced_free_col:
            return v.cr.barycenter  # type: ignore
        else:
            return H.expanded_fixed_col.index(v)

    H.N.sort(key=pos)
    H.S.sort(key=pos)

    south_indicies = {k: i for i, k in enumerate(H.S)}
    north_indicies = {k: i for i, k in enumerate(H.N)}

    edges.sort(key=lambda e: south_indicies[e[1]])
    edges.sort(key=lambda e: north_indicies[e[0]])

    first_idx = 1
    while first_idx < len(H.S):
        first_idx *= 2

    tree = [0] * (2 * first_idx - 1)
    first_idx -= 1

    cross_weight = 0
    for _, v, weight in edges:
        idx = south_indicies[v] + first_idx
        tree[idx] += weight
        weight_sum = 0
        while idx > 0:
            if idx % 2 == 1:
                weight_sum += tree[idx + 1]

            idx = (idx - 1) // 2
            tree[idx] += weight

        cross_weight += weight * weight_sum

    return cross_weight


def get_new_col_order(v: GNode | Cluster, LT: _MixedGraph) -> Iterator[GNode]:
    if v.type == GType.CLUSTER:
        for w in sorted(LT[v], key=get_barycenter):
            yield from get_new_col_order(w, LT)
    else:
        yield v


@cache
def non_cluster_descendant(T: _MixedGraph, c: Cluster) -> GNode:
    return next(v for _, v in nx.bfs_edges(T, c) if v.type != GType.CLUSTER)


def sort_internal_columns(items: _FreeColumns) -> None:
    for free_col, LT, data in items:

        def pos(v: GNode | Cluster) -> int:
            w = non_cluster_descendant(LT, v) if v.type == GType.CLUSTER else v
            return free_col.index(w)

        for H in data:
            H.reduced_free_col.sort(key=pos)


# -------------------------------------------------------------------


def minimized_cross_count(
  columns: Sequence[list[GNode]],
  forward_items: _FreeColumns,
  backward_items: _FreeColumns,
  T: _MixedGraph,
) -> float:
    cross_count = inf
    is_forwards = random.choice((True, False))
    is_first_sweep = True
    while True:
        for v in T:
            v.cr.reset()

        if cross_count == 0:
            return 0

        is_forwards = not is_forwards
        old_cross_count = cross_count
        cross_count = 0

        items = forward_items if is_forwards else backward_items
        for i, (free_col, LT, data) in enumerate(items):
            if i == 0:
                fixed_col = columns[0] if is_forwards else columns[-1]
                clusters = {c: j for j, v in enumerate(fixed_col) for c in nx.ancestors(T, v)}
                key = cast(Callable[[Cluster], int], clusters.get)
            else:
                key = get_barycenter

            for H in data:
                H.constrained_clusters.sort(key=key)
                sort_expanded_fixed_col(H)

                calc_socket_ranks(H, is_forwards)
                calc_barycenters(H)
                fill_in_unknown_barycenters(H.reduced_free_col, is_first_sweep)
                handle_constraints(H)

                cross_count += get_cross_count(H)

            root = topologically_sorted_clusters(LT)[0]
            new_order = tuple(get_new_col_order(root, LT))
            free_col.sort(key=new_order.index)

        if old_cross_count > cross_count:
            sort_internal_columns(forward_items + backward_items)
            best_columns = [c.copy() for c in columns]
            is_first_sweep = False
        else:
            for first_col, best_col in zip(columns, best_columns):
                first_col.sort(key=best_col.index)
            break

    return old_cross_count


def minimize_crossings(G: nx.MultiDiGraph[GNode], T: _MixedGraph) -> None:
    columns = G.graph['columns']
    trees = get_col_nesting_trees(columns, T)
    G_ = G.copy()

    expand_multi_inputs(G_)

    forward_data = crossing_reduction_data(G_, trees)
    forward_items = list(zip(columns[1:], trees[1:], forward_data))

    trees.reverse()
    backward_data = crossing_reduction_data(nx.reverse_view(G_), trees, True)  # type: ignore
    backward_items = list(zip(columns[-2::-1], trees[1:], backward_data))

    # -------------------------------------------------------------------

    random.seed(0)
    best_cross_count = inf
    best_columns = [c.copy() for c in columns]
    for _ in range(config.SETTINGS.iterations):
        cross_count = minimized_cross_count(columns, forward_items, backward_items, T)
        if cross_count < best_cross_count:
            best_cross_count = cross_count
            best_columns = [c.copy() for c in columns]
            if best_cross_count == 0:
                break
        else:
            for col, best_col in zip(columns, best_columns):
                col.sort(key=best_col.index)
            sort_internal_columns(forward_items + backward_items)
