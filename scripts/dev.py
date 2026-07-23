#!/usr/bin/env python3
"""
Development server script for LangGraph.

This script automatically installs langgraph-cli if not present
and starts the development server with hot reloading enabled.
"""

import shutil
import subprocess
import sys
from typing import NoReturn


def is_langgraph_installed() -> bool:
    """Check if the langgraph CLI is installed and available in PATH."""
    return shutil.which("langgraph") is not None


def install_langgraph_cli() -> None:
    """Install langgraph-cli with inmem extra for development mode."""
    print("LangGraph CLI not found. Installing langgraph-cli[inmem]...")

    install_command = [sys.executable, "-m", "pip", "install", "langgraph-cli[inmem]"]

    try:
        subprocess.run(install_command, check=True)
        print("LangGraph CLI installed successfully.")
    except subprocess.CalledProcessError as error:
        print(f"Failed to install langgraph-cli: {error}")
        sys.exit(1)


def ensure_nltk_data() -> None:
    """Pre-download NLTK punkt tokenizer data if missing."""
    import nltk
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        print("Downloading NLTK punkt tokenizer data...")
        nltk.download("punkt_tab", quiet=True)


def start_development_server() -> NoReturn:
    """Start the LangGraph development server with hot reloading."""
    print("Starting LangGraph development server...")

    dev_command = ["langgraph", "dev", "--no-browser", "--allow-blocking"]

    try:
        subprocess.run(dev_command, check=True)
    except subprocess.CalledProcessError as error:
        print(f"Failed to start development server: {error}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nDevelopment server stopped.")
        sys.exit(0)


def main() -> None:
    """Main entry point for the development server script."""
    if not is_langgraph_installed():
        install_langgraph_cli()

    ensure_nltk_data()
    start_development_server()


if __name__ == "__main__":
    main()
