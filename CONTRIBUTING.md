# Contributing to zx

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/vcpandya/aicmd.git
cd aicmd

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in editable mode with all optional dependencies
pip install -e ".[all]"

# Verify installation
zx --version
```

## Project Structure

```
src/zx/
  ai.py          # AI integration (LiteLLM + google-genai fallback)
  cli.py         # Typer CLI entry point
  config.py      # Configuration management
  cost.py        # Cost tracking and budget enforcement
  safety.py      # Command risk analysis
  executor.py    # Command execution
  planner.py     # Multi-step plan orchestration
  ui.py          # Rich terminal UI
  undo.py        # Plan reversal (time-travel undo)
  ...            # Additional feature modules
```

## Making Changes

1. Fork the repo and create a feature branch
2. Make your changes
3. Run syntax checks: `python -c "import ast, glob; [ast.parse(open(f).read()) for f in glob.glob('src/zx/*.py')]"`
4. Test with a local model: `zx --model ollama_chat/gemma3 "your test prompt"`
5. Submit a pull request

## Adding a New Provider

zx uses LiteLLM, so most providers work out of the box. If you need special handling:

1. Add the provider prefix to `PROVIDER_ENV_MAP` in `config.py`
2. Add env var detection in `get_provider_config()`
3. Test with the provider

## Code Style

- Keep it simple — avoid over-engineering
- Follow existing patterns in the codebase
- Use type hints for public function signatures
- Add docstrings for public classes and functions

## Reporting Issues

- Use GitHub Issues: https://github.com/vcpandya/aicmd/issues
- Include your Python version, OS, and the command you ran
- Include the full error output

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
