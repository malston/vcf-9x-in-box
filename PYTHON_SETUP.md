# Python Setup with uv

This project uses [uv](https://github.com/astral-sh/uv) for fast Python package management.

## Quick Start

### 1. Install uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv

# Or with pip
pip install uv
```

### 2. Install Dependencies

```bash
# Install all dependencies from pyproject.toml
uv pip install -e .

# Or sync with uv (creates/updates .venv automatically)
uv sync
```

### 3. Run Scripts

```bash
# Using uv run (no activation needed)
uv run scripts/generate_kickstart.py

# Or activate the virtual environment first
source .venv/bin/activate
./scripts/generate_kickstart.py
```

## Common Commands

```bash
# Install project in editable mode
uv pip install -e .

# Add a new dependency
uv add <package-name>

# Update all dependencies
uv pip install --upgrade -e .

# Create/sync virtual environment
uv sync

# Run script without activating venv
uv run python scripts/generate_kickstart.py

# Run script as console script
uv run generate-kickstart
```

## Using the Kickstart Generator

```bash
# Generate all ESXi kickstart configs
uv run scripts/generate_kickstart.py

# Generate specific host
uv run scripts/generate_kickstart.py 3

# Generate to custom directory
uv run scripts/generate_kickstart.py all /tmp

# Show help
uv run scripts/generate_kickstart.py --help
```

## Why uv?

- **Fast**: 10-100x faster than pip
- **Modern**: Uses pyproject.toml standard
- **Reliable**: Better dependency resolution
- **Simple**: One tool for everything

## Project Structure

```sh
.
├── pyproject.toml          # Project metadata and dependencies
├── scripts/
│   └── generate_kickstart.py
├── config/
│   └── ks-template.cfg.j2  # Jinja2 template
└── .venv/                  # Virtual environment (auto-created by uv)
```
