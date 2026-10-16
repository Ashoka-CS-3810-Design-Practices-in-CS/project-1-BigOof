import pytest

from big_o.back import MetroGraph, fastestRoute, fewestInterchangesRoute


@pytest.fixture
def graph():
    graph = MetroGraph()

    for code in ("A", "B", "C", "D"):
        graph.add_station(code, f"Station {code}")

    # Fast route: one interchange, total time 4.
    graph.add_connection("A", "B", 2, "red")
    graph.add_connection("B", "D", 2, "blue")

    # Slower route: no interchanges, total time 6.
    graph.add_connection("A", "C", 3, "green")
    graph.add_connection("C", "D", 3, "green")

    return graph


def test_fastest_route(graph):
    result = graph.fastestRoute("A", "D")

    assert result.stations == ("A", "B", "D")
    assert result.total_time == 4
    assert result.interchanges == 1


def test_fewest_interchanges_route(graph):
    result = graph.fewestInterchangesRoute("A", "D")

    assert result.stations == ("A", "C", "D")
    assert result.total_time == 6
    assert result.interchanges == 0


def test_route_segments_match_stations(graph):
    result = graph.fastestRoute("A", "D")

    assert len(result.segments) == len(result.stations) - 1

    for i, segment in enumerate(result.segments):
        assert segment.from_station == result.stations[i]
        assert segment.to_station == result.stations[i + 1]


def test_source_equals_destination(graph):
    result = graph.fastestRoute("A", "A")

    assert result.stations == ("A",)
    assert result.segments == ()
    assert result.total_time == 0
    assert result.interchanges == 0


def test_unknown_station(graph):
    with pytest.raises(KeyError, match="Unknown station"):
        graph.fastestRoute("A", "UNKNOWN")


def test_disconnected_stations():
    graph = MetroGraph()
    graph.add_station("A", "Station A")
    graph.add_station("B", "Station B")

    with pytest.raises(ValueError, match="No route"):
        graph.fastestRoute("A", "B")


def test_duplicate_station_rejected(graph):
    with pytest.raises(ValueError, match="already exists"):
        graph.add_station("A", "Duplicate A")


def test_negative_travel_time_rejected(graph):
    with pytest.raises(ValueError, match="non-negative"):
        graph.add_connection("A", "B", -1, "red")


def test_connections_are_bidirectional(graph):
    result = graph.fastestRoute("D", "A")

    assert result.stations == ("D", "B", "A")
    assert result.total_time == 4


def test_interchange_count(graph):
    # A-B is red and B-D is blue: exactly one change, at B.
    result = graph.fastestRoute("A", "D")

    assert [segment.line for segment in result.segments] == ["red", "blue"]
    assert result.interchanges == 1


def test_fewest_interchanges_disconnected_stations():
    graph = MetroGraph()
    graph.add_station("A", "Station A")
    graph.add_station("B", "Station B")

    with pytest.raises(ValueError, match="No route"):
        graph.fewestInterchangesRoute("A", "B")


def test_fewest_interchanges_unknown_station(graph):
    with pytest.raises(KeyError, match="Unknown station"):
        graph.fewestInterchangesRoute("A", "UNKNOWN")


def test_connection_to_unknown_station_rejected(graph):
    with pytest.raises(KeyError, match="Both stations"):
        graph.add_connection("A", "UNKNOWN", 1, "red")


def test_connection_without_line_rejected(graph):
    with pytest.raises(ValueError, match="metro line"):
        graph.add_connection("A", "B", 1, "")


def test_module_level_wrappers(graph):
    assert fastestRoute(graph, "A", "D") == graph.fastestRoute("A", "D")
    assert fewestInterchangesRoute(graph, "A", "D") == graph.fewestInterchangesRoute("A", "D")



def test_route_via_fastest(graph):
    # A -> D -> C: fastest is A-B-D (4) then D-C (3).
    result = graph.routeVia(["A", "D", "C"])

    assert result.stations == ("A", "B", "D", "C")
    assert result.total_time == 7
    assert result.interchanges == 2


def test_route_via_forces_detour(graph):
    # The fastest A -> D route skips C; routing via C must pass through it.
    result = graph.routeVia(["A", "C", "D"])

    assert result.stations == ("A", "C", "D")
    assert result.total_time == 6


def test_route_via_fewest_interchanges(graph):
    result = graph.routeVia(["A", "B", "D"], fewest_interchanges=True)

    assert result.stations == ("A", "B", "D")
    assert result.interchanges == 1


def test_route_via_optimises_line_at_intermediate_stop():
    # From A, reaching X is equally fast on red or green, but only green
    # continues to Z. Optimising the legs separately could arrive on red and
    # count an extra change at X; the joint search should not.
    graph = MetroGraph()
    for code in ("A", "X", "Z"):
        graph.add_station(code, code)
    graph.add_connection("A", "X", 1, "red")
    graph.add_connection("A", "X", 1, "green")
    graph.add_connection("X", "Z", 1, "green")

    result = graph.routeVia(["A", "X", "Z"], fewest_interchanges=True)

    assert result.interchanges == 0
    assert [segment.line for segment in result.segments] == ["green", "green"]


def test_route_via_can_revisit_stations(graph):
    result = graph.routeVia(["A", "B", "A"])

    assert result.stations == ("A", "B", "A")
    assert result.total_time == 4


def test_route_via_segments_match_stations(graph):
    result = graph.routeVia(["A", "C", "B"])

    for i, segment in enumerate(result.segments):
        assert segment.from_station == result.stations[i]
        assert segment.to_station == result.stations[i + 1]


def test_route_via_rejects_unknown_station(graph):
    with pytest.raises(KeyError, match="Unknown station"):
        graph.routeVia(["A", "Z", "D"])


def test_route_via_rejects_repeated_consecutive_stop(graph):
    with pytest.raises(ValueError, match="Consecutive stops"):
        graph.routeVia(["A", "A", "D"])


def test_route_via_unreachable_stop():
    graph = MetroGraph()
    for code in ("A", "B", "C"):
        graph.add_station(code, code)
    graph.add_connection("A", "B", 1, "red")

    with pytest.raises(ValueError, match="No route"):
        graph.routeVia(["A", "C", "B"])


@pytest.mark.parametrize("stops", [[], ["A"]])
def test_route_via_needs_two_stops(graph, stops):
    with pytest.raises(ValueError, match="at least a source and a destination"):
        graph.routeVia(stops)


@pytest.fixture
def walk_graph():
    # A -red- B ~walk~ C -blue- D, plus C -red- E.
    graph = MetroGraph()
    for code in ("A", "B", "C", "D", "E"):
        graph.add_station(code, f"Station {code}")
    graph.add_connection("A", "B", 2, "red")
    graph.add_connection("B", "C", 5, "walk", walk=True)
    graph.add_connection("C", "D", 2, "blue")
    graph.add_connection("C", "E", 2, "red")
    return graph


@pytest.mark.parametrize("route", ["fastestRoute", "fewestInterchangesRoute"])
def test_walk_between_lines_is_one_interchange(walk_graph, route):
    result = getattr(walk_graph, route)("A", "D")

    assert result.stations == ("A", "B", "C", "D")
    assert [segment.walk for segment in result.segments] == [False, True, False]
    assert result.total_time == 9
    assert result.interchanges == 1


def test_walk_back_to_same_line_is_not_an_interchange(walk_graph):
    result = walk_graph.fewestInterchangesRoute("A", "E")

    assert result.stations == ("A", "B", "C", "E")
    assert result.interchanges == 0


def test_walk_from_source_is_not_an_interchange(walk_graph):
    result = walk_graph.fewestInterchangesRoute("B", "D")

    assert result.stations == ("B", "C", "D")
    assert result.interchanges == 0


def test_route_via_counts_walk_like_other_searches(walk_graph):
    result = walk_graph.routeVia(["A", "C", "D"], fewest_interchanges=True)

    assert result.stations == ("A", "B", "C", "D")
    assert result.segments[1].walk
    assert result.interchanges == 1


@pytest.fixture
def stale_queue_graph():
    # B is first queued at cost 5 (via A-B) and then improved to 2 (via C), so
    # the cost-5 entry is popped later and must be skipped.
    graph = MetroGraph()
    for code in ("A", "B", "C", "D"):
        graph.add_station(code, code)
    graph.add_connection("A", "B", 5, "red")
    graph.add_connection("A", "C", 1, "red")
    graph.add_connection("C", "B", 1, "red")
    graph.add_connection("B", "D", 10, "red")
    return graph


def test_fastest_route_skips_outdated_queue_entries(stale_queue_graph):
    result = stale_queue_graph.fastestRoute("A", "D")

    assert result.stations == ("A", "C", "B", "D")
    assert result.total_time == 12


def test_route_via_skips_outdated_queue_entries(stale_queue_graph):
    result = stale_queue_graph.routeVia(["A", "B", "D"])

    assert result.stations == ("A", "C", "B", "D")
    assert result.total_time == 12
