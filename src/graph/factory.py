"""Graph backend factory."""
import os
from src.graph.base import GraphBackend


def get_backend(persist: bool = True) -> GraphBackend:
    backend = os.getenv("GRAPH_BACKEND", "networkx")
    if backend == "neo4j":
        from src.graph.neo4j_backend import Neo4jBackend
        return Neo4jBackend()
    from src.graph.networkx_backend import NetworkXBackend
    return NetworkXBackend(persist=persist)
