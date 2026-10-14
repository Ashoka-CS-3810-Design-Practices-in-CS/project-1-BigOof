from dataclasses import dataclass
import heapq
from math import inf
from typing import Hashable, Optional


StationId = Hashable


@dataclass(frozen=True)
class Station:
	"""A metro station identified by its unique code."""

	code: StationId
	name: str
	lines: frozenset[str]

	def __init__(self, code: StationId, name: str, lines: set[str] | list[str] | tuple[str, ...] = ()):
		object.__setattr__(self, "code", code)
		object.__setattr__(self, "name", name)
		object.__setattr__(self, "lines", frozenset(lines))


@dataclass(frozen=True)
class Edge:
	"""A direct connection to a neighbouring station."""

	station: StationId
	travel_time: float
	line: str


@dataclass(frozen=True)
class RouteSegment:
	"""One travelled edge in a reconstructed route."""

	from_station: StationId
	to_station: StationId
	travel_time: float
	line: str


@dataclass(frozen=True)
class RouteResult:
	"""The route and the totals produced by either route algorithm."""

	stations: tuple[StationId, ...]
	segments: tuple[RouteSegment, ...]
	total_time: float
	interchanges: int


class MetroGraph:
	"""Adjacency-list representation of a metro network."""

	def __init__(self) -> None:
		self.stations: dict[StationId, Station] = {}
		self.adjacency: dict[StationId, list[Edge]] = {}

	def add_station(
		self,
		code: StationId,
		name: str,
		lines: set[str] | list[str] | tuple[str, ...] = (),
	) -> Station:
		if code in self.stations:
			raise ValueError(f"Station code already exists: {code!r}")
		station = Station(code, name, lines)
		self.stations[code] = station
		self.adjacency[code] = []
		return station

	def add_connection(
		self,
		first: StationId,
		second: StationId,
		travel_time: float,
		line: str,
	) -> None:
		"""Add a bidirectional connection on ``line``."""
		if first not in self.stations or second not in self.stations:
			raise KeyError("Both stations must be added before connecting them")
		if travel_time < 0:
			raise ValueError("Travel time must be non-negative")
		if not line:
			raise ValueError("A connection must have a metro line")

		self.adjacency[first].append(Edge(second, travel_time, line))
		self.adjacency[second].append(Edge(first, travel_time, line))

	def fastestRoute(self, source: StationId, destination: StationId) -> RouteResult:
		"""Return the route with minimum total estimated travel time."""
		self._check_stations(source, destination)
		distances: dict[StationId, float] = {code: inf for code in self.stations}
		predecessors: dict[StationId, tuple[StationId, Edge]] = {}
		distances[source] = 0
		queue: list[tuple[float, int, StationId]] = [(0, 0, source)]
		sequence = 1

		while queue:
			distance, _, current = heapq.heappop(queue)
			if distance != distances[current]:
				continue
			if current == destination:
				break
			for edge in self.adjacency[current]:
				new_distance = distance + edge.travel_time
				if new_distance < distances[edge.station]:
					distances[edge.station] = new_distance
					predecessors[edge.station] = (current, edge)
					heapq.heappush(queue, (new_distance, sequence, edge.station))
					sequence += 1

		if distances[destination] == inf:
			raise ValueError(f"No route from {source!r} to {destination!r}")
		return self._reconstruct(source, destination, predecessors)

	def fewestInterchangesRoute(self, source: StationId, destination: StationId) -> RouteResult:
		"""Return the route minimising interchanges, then travel time."""
		self._check_stations(source, destination)
		start = (source, None)
		distances: dict[tuple[StationId, Optional[str]], tuple[int, float]] = {
			start: (0, 0)
		}
		predecessors: dict[
			tuple[StationId, Optional[str]],
			tuple[tuple[StationId, Optional[str]], Edge],
		] = {}
		queue: list[tuple[int, float, int, StationId, Optional[str]]] = [(0, 0, 0, source, None)]
		sequence = 1
		destination_state: Optional[tuple[StationId, Optional[str]]] = None

		while queue:
			changes, time, _, current, arrival_line = heapq.heappop(queue)
			state = (current, arrival_line)
			if (changes, time) != distances.get(state):
				continue
			if current == destination:
				destination_state = state
				break
			for edge in self.adjacency[current]:
				next_state = (edge.station, edge.line)
				added_change = int(arrival_line is not None and arrival_line != edge.line)
				candidate = (changes + added_change, time + edge.travel_time)
				if candidate < distances.get(next_state, (inf, inf)):
					distances[next_state] = candidate
					predecessors[next_state] = (state, edge)
					heapq.heappush(
						queue,
						(candidate[0], candidate[1], sequence, edge.station, edge.line),
					)
					sequence += 1

		if destination_state is None:
			raise ValueError(f"No route from {source!r} to {destination!r}")
		return self._reconstruct_augmented(source, destination_state, predecessors)

	def _check_stations(self, source: StationId, destination: StationId) -> None:
		missing = [code for code in (source, destination) if code not in self.stations]
		if missing:
			raise KeyError(f"Unknown station code(s): {missing}")

	def _reconstruct(
		self,
		source: StationId,
		destination: StationId,
		predecessors: dict[StationId, tuple[StationId, Edge]],
	) -> RouteResult:
		states: list[tuple[StationId, Edge]] = []
		current = destination
		while current != source:
			previous, edge = predecessors[current]
			states.append((previous, edge))
			current = previous
		states.reverse()
		segments = tuple(RouteSegment(previous, edge.station, edge.travel_time, edge.line) for previous, edge in states)
		return self._result(source, segments)

	def _reconstruct_augmented(
		self,
		source: StationId,
		destination_state: tuple[StationId, Optional[str]],
		predecessors: dict[tuple[StationId, Optional[str]], tuple[tuple[StationId, Optional[str]], Edge]],
	) -> RouteResult:
		states: list[tuple[StationId, Edge]] = []
		current = destination_state
		while current[0] != source or current[1] is not None:
			previous, edge = predecessors[current]
			states.append((previous[0], edge))
			current = previous
		states.reverse()
		segments = tuple(RouteSegment(previous, edge.station, edge.travel_time, edge.line) for previous, edge in states)
		return self._result(source, segments)

	@staticmethod
	def _result(source: StationId, segments: tuple[RouteSegment, ...]) -> RouteResult:
		stations = [source]
		for segment in segments:
			stations.append(segment.to_station)
		interchanges = sum(
			previous.line != current.line
			for previous, current in zip(segments, segments[1:])
		)
		return RouteResult(
			tuple(stations),
			segments,
			sum(segment.travel_time for segment in segments),
			interchanges,
		)


def fastestRoute(graph: MetroGraph, source: StationId, destination: StationId) -> RouteResult:
	"""Top-level wrapper for the standard Dijkstra route."""
	return graph.fastestRoute(source, destination)


def fewestInterchangesRoute(
	graph: MetroGraph,
	source: StationId,
	destination: StationId,
) -> RouteResult:
	"""Top-level wrapper for state-augmented Dijkstra."""
	return graph.fewestInterchangesRoute(source, destination)
