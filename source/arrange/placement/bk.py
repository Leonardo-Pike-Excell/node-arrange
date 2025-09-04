# SPDX-License-Identifier: GPL-2.0-or-later

# http://dx.doi.org/10.1007/3-540-45848-4_3
# http://dx.doi.org/10.1007/978-3-319-27261-0_12
# https://arxiv.org/abs/2008.01252

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Collection, Iterator, Sequence
from itertools import pairwise
from math import ceil, floor, inf
from statistics import fmean
from typing import Any, cast

import networkx as nx

from ... import config
from ..graph import FROM_SOCKET, TO_SOCKET, Edge, GNode, GType, Socket


def marked_conflicts(
  G: nx.DiGraph[GNode],
  *,
  should_ensure_alignment: Callable[[GNode], Any],
) -> set[frozenset[GNode]]:
    columns = G.graph['columns']
    marked_edges = set()
    for i, col in enumerate(columns[1:], 1):
        k_0 = 0
        l = 0
        for l_1, u in enumerate(col):
            if should_ensure_alignment(u):
                upper_nbr = next(iter(G.pred[u]))
                k_1 = upper_nbr.col.index(upper_nbr)
            elif u == col[-1]:
                k_1 = len(columns[i - 1]) - 1
            else:
                continue

            while l <= l_1:
                v = col[l]
                l += 1

                if should_ensure_alignment(v):
                    continue

                for pred in G.pred[v]:
                    k = pred.col.index(pred)
                    if k < k_0 or k > k_1:
                        marked_edges.add(frozenset((pred, v)))

            k_0 = k_1

    return marked_edges


def horizontal_alignment(
  G: nx.DiGraph[GNode],
  marked_edges: Collection[frozenset[GNode]],
) -> None:
    for col in G.graph['columns']:
        prev_i = -1
        for v in col:
            predecessors = sorted(G.pred[v], key=lambda u: u.col.index(u))
            m = (len(predecessors) - 1) / 2
            for u in predecessors[floor(m):ceil(m) + 1]:
                i = u.col.index(u)

                if v.aligned != v or {u, v} in marked_edges or prev_i >= i:
                    continue

                u.aligned = v
                v.root = u.root
                v.aligned = v.root
                prev_i = i


def iter_block(start: GNode) -> Iterator[GNode]:
    yield start
    w = start
    while (w := w.aligned) != start:
        yield w


def should_use_inner_shift(v: GNode, w: GNode, is_right: bool) -> bool:
    if v.is_reroute or w.is_reroute:
        return True

    if not is_right:
        v, w = w, v

    if v.height > w.height and not getattr(w.node, 'hide', False):
        return False

    return abs(v.height - w.height) > fmean((v.height, w.height)) / 2


def inner_shift(G: nx.MultiDiGraph[GNode], is_right: bool, is_up: bool) -> None:
    for root in {v.root for v in G}:
        for v, w in pairwise(iter_block(root)):
            if not should_use_inner_shift(v, w, is_right):
                w.inner_shift = v.inner_shift
                continue

            inner_shifts = []
            for k in G[v][w]:
                p: Socket = G[v][w][k][FROM_SOCKET]
                q: Socket = G[v][w][k][TO_SOCKET]
                if p.owner != v:
                    p, q = q, p

                if is_up:
                    inner_shifts.append(v.inner_shift - p._offset_y + q._offset_y)
                else:
                    inner_shifts.append(v.inner_shift + p._offset_y - q._offset_y)

            w.inner_shift = fmean(inner_shifts)


def place_block(v: GNode, is_up: bool) -> None:
    if cast(float | None, v.y) is not None:
        return

    v.y = 0
    initial = True
    w = v
    while True:
        i = w.col.index(w)
        if i > 0:
            n = w.col[i - 1]
            u = n.root
            place_block(u, is_up)

            if v.sink == v:
                v.sink = u.sink

            if v.sink == u.sink:
                delta_l = n.height + config.MARGIN.y if is_up else w.height + config.MARGIN.y
                s_b = u.y + n.inner_shift - w.inner_shift + delta_l
                v.y = s_b if initial else max(v.y, s_b)
                initial = False

        w = w.aligned
        if w == v:
            break

    while (w := w.aligned) != v:
        w.y = v.y
        w.sink = v.sink


def vertical_compaction(G: nx.DiGraph[GNode], is_up: bool) -> None:
    for v in G:
        if v.root == v:
            place_block(v, is_up)

    columns = G.graph['columns']
    neighborings: defaultdict[tuple[GNode, ...], set[Edge]] = defaultdict(set)

    for col in columns:
        for v, u in pairwise(reversed(col)):
            if u.sink != v.sink:
                neighborings[tuple(v.sink.col)].add((u, v))

    for col in columns:
        if col[0].sink.shift == inf:
            col[0].sink.shift = 0

        for u, v in neighborings[tuple(col)]:
            delta_l = u.height + config.MARGIN.y if is_up else v.height + config.MARGIN.y
            s_c = v.y + v.inner_shift - u.y - u.inner_shift - delta_l
            u.sink.shift = min(u.sink.shift, v.sink.shift + s_c)

    for v in G:
        v.y += v.sink.shift + v.inner_shift


def balance(G: nx.DiGraph[GNode], layouts: list[list[float]]) -> None:

    def min_y(layout: Sequence[float]) -> float:
        return min([y - v.height for v, y in zip(G, layout)])

    smallest_layout = min(layouts, key=lambda l: max(l) - min_y(l))

    movement = min_y(smallest_layout)
    for i in range(len(smallest_layout)):
        smallest_layout[i] -= movement

    for i, layout in enumerate(layouts):
        if layout == smallest_layout:
            continue

        func = min_y if i % 2 != 1 else max
        movement = func(smallest_layout) - func(layout)
        for j in range(len(layout)):
            layout[j] += movement


def bk_assign_y_coords(G: nx.MultiDiGraph[GNode]) -> None:
    columns = G.graph['columns']
    for col in columns:
        col.reverse()

    is_incident_to_inner_segment = lambda v: v.is_reroute and any(u.is_reroute for u in G.pred[v])
    is_incident_to_vertical_border = lambda v: v.type == GType.VERTICAL_BORDER and G.pred[v]
    marked_edges = marked_conflicts(G, should_ensure_alignment=is_incident_to_inner_segment)
    marked_edges |= marked_conflicts(G, should_ensure_alignment=is_incident_to_vertical_border)

    layouts = []
    for dir_x in (-1, 1):
        G = nx.reverse_view(G)  # type: ignore
        columns.reverse()
        for dir_y in (-1, 1):
            horizontal_alignment(G, marked_edges)
            is_up = dir_y == 1
            inner_shift(G, dir_x == 1, is_up)
            vertical_compaction(G, is_up)
            layouts.append([v.y * -dir_y for v in G])

            for v in G:
                v.reset()

            for col in columns:
                col.reverse()

    for col in columns:
        col.reverse()

    if not config.SETTINGS.balance:
        for v, y in zip(G, layouts[1]):
            v.y = y
        return

    balance(G, layouts)
    for i, v in enumerate(G):
        values = [l[i] for l in layouts]
        values.sort()
        v.y = fmean(values[1:3])
