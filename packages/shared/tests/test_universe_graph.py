import json
from pathlib import Path

from gank_shared.universe_graph import bfs_jump_distance, load_graph

# A tiny hand-built system graph: 1-2-3-4 in a line, plus an isolated
# system 99 (no stargates -- e.g. wormhole space) and a branch 2-5.
GRAPH = {
    1: [2],
    2: [1, 3, 5],
    3: [2, 4],
    4: [3],
    5: [2],
}


def test_same_system_is_zero_jumps():
    assert bfs_jump_distance(GRAPH, 1, 1) == 0


def test_direct_neighbor_is_one_jump():
    assert bfs_jump_distance(GRAPH, 1, 2) == 1


def test_shortest_path_across_multiple_hops():
    assert bfs_jump_distance(GRAPH, 1, 4) == 3


def test_branch_is_shortest_not_longest():
    assert bfs_jump_distance(GRAPH, 1, 5) == 2


def test_unknown_system_returns_none():
    assert bfs_jump_distance(GRAPH, 1, 99999) is None
    assert bfs_jump_distance(GRAPH, 99999, 1) is None


def test_load_graph_round_trips_int_keys(tmp_path: Path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({"1": [2, 3], "2": [1], "3": [1]}))

    loaded = load_graph(path)

    assert loaded == {1: [2, 3], 2: [1], 3: [1]}
    assert bfs_jump_distance(loaded, 2, 3) == 2
