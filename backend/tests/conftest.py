import pytest


@pytest.fixture(autouse=True)
def _no_crawler(monkeypatch):
    monkeypatch.setenv("SHIMACLIPS_CRAWLER", "0")
