"""Data source adapter factory."""
import os
from src.datasource.base import DataSourceAdapter


def get_adapter() -> DataSourceAdapter:
    mode = os.getenv("DATASOURCE_MODE", "dummy")
    if mode == "jira":
        from src.datasource.jira_adapter import JiraAdapter
        return JiraAdapter()
    from src.datasource.dummy_adapter import DummyAdapter
    return DummyAdapter()
