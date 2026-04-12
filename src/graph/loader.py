"""Load dummy tickets + pre-computed edges into the graph backend."""
from src.datasource.dummy_adapter import DummyAdapter
from src.graph.base import GraphBackend
from src.models.ontology import OntologyNode


def load_dummy_graph(backend: GraphBackend) -> None:
    """Populate the graph from the Ulysses dummy data (tickets + pre-computed edges)."""
    adapter = DummyAdapter()
    tickets = adapter.fetch_all_tickets()
    edges = adapter.fetch_pre_computed_edges()

    for ticket in tickets:
        node = OntologyNode(
            id=ticket.id,
            type=ticket.type,  # type: ignore[arg-type]
            name=ticket.summary,
            description=ticket.description,
            status=ticket.status,
            labels=ticket.labels,
        )
        backend.merge_node(node)

    for edge in edges:
        backend.merge_edge(edge)
