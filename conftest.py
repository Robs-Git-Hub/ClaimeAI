"""Root conftest: registers custom pytest markers and ensures the repo root
is on sys.path so top-level packages (ingest, scripts) are importable in tests.
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (e.g. docling model download on first run); "
        'deselect with -m "not slow"',
    )
