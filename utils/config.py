"""Load non-sensitive pipeline configuration from config.toml.

Secrets (API keys) stay in ``.env``. This module handles everything
else: provider selection, model tier mappings, search settings, and
reasoning effort configuration.

Priority: environment variables override config.toml values (handled
by Pydantic in ``settings.py``). If ``config.toml`` is missing, all
consumers fall back to hardcoded defaults.
"""

import tomllib
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


def _load_config(path: Path = _CONFIG_PATH) -> dict:
    """Load config from a TOML file.

    Returns an empty dict when the file does not exist. Raises
    ``tomllib.TOMLDecodeError`` on malformed TOML so configuration
    typos surface immediately rather than falling through to defaults.
    """
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


config = _load_config()
