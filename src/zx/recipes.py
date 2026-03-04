"""Workflow recipe system for zx — save, replay, export, and import multi-step plans."""

import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .config import CONFIG_DIR

RECIPES_DIR = CONFIG_DIR / "recipes"


@dataclass
class RecipeStep:
    """A single step in a recipe."""
    command: str
    explanation: str
    is_reversible: bool = False
    undo_command: str = ""


@dataclass
class Recipe:
    """A reusable workflow recipe."""
    name: str
    description: str
    steps: list[RecipeStep]
    parameters: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source_prompt: str = ""
    created: str = ""
    success_count: int = 1
    author: str = ""              # "github:username" or "anonymous"
    community_id: str = ""        # "{category}/{name}" if from community
    source: str = "local"         # "local" or "community"

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Recipe":
        steps = [RecipeStep(**s) for s in data.pop("steps", [])]
        return cls(steps=steps, **{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _recipe_path(name: str) -> Path:
    """Get the file path for a recipe by name."""
    safe_name = re.sub(r'[^\w\-]', '_', name)
    return RECIPES_DIR / f"{safe_name}.json"


def save_recipe(recipe: Recipe) -> Path:
    """Save a recipe to disk."""
    RECIPES_DIR.mkdir(parents=True, exist_ok=True)
    if not recipe.created:
        recipe.created = datetime.now(timezone.utc).isoformat()
    path = _recipe_path(recipe.name)
    path.write_text(json.dumps(recipe.to_dict(), indent=2))
    return path


def load_recipe(name: str) -> Optional[Recipe]:
    """Load a recipe by name."""
    path = _recipe_path(name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return Recipe.from_dict(data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def list_recipes() -> list[Recipe]:
    """List all saved recipes."""
    if not RECIPES_DIR.exists():
        return []
    recipes = []
    for f in sorted(RECIPES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            recipes.append(Recipe.from_dict(data))
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    return recipes


def delete_recipe(name: str) -> bool:
    """Delete a recipe by name. Returns True if deleted."""
    path = _recipe_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


def export_recipe(name: str, output_path: Optional[str] = None) -> Optional[str]:
    """Export a recipe as a .zxrecipe file. Returns the output path or None."""
    recipe = load_recipe(name)
    if not recipe:
        return None
    out = Path(output_path) if output_path else Path.cwd() / f"{recipe.name}.zxrecipe"
    out.write_text(json.dumps(recipe.to_dict(), indent=2))
    return str(out)


def import_recipe(file_path: str) -> Optional[Recipe]:
    """Import a recipe from a .zxrecipe file."""
    path = Path(file_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        recipe = Recipe.from_dict(data)
        save_recipe(recipe)
        return recipe
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def substitute_params(command: str, params: dict[str, str]) -> str:
    """Replace {{param}} placeholders in a command with actual values."""
    result = command
    for key, value in params.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


def replay_recipe(
    recipe: Recipe,
    params: dict[str, str],
    execute_fn,
    on_stdout=None,
    on_stderr=None,
    confirm_fn=None,
) -> list[dict]:
    """Replay a recipe with parameter substitution.

    Args:
        recipe: The recipe to replay
        params: Parameter values for substitution
        execute_fn: Function to execute commands (executor.execute_command)
        on_stdout: Callback for stdout lines
        on_stderr: Callback for stderr lines
        confirm_fn: Optional function that takes (command, risk, explanation) and returns 'y'/'n'/'c'

    Returns:
        List of step results [{"command": ..., "return_code": ..., "stdout": ..., "stderr": ...}]
    """
    from .safety import analyze_risk

    results = []
    for i, step in enumerate(recipe.steps, 1):
        command = substitute_params(step.command, params)
        risk = analyze_risk(command)

        if confirm_fn:
            choice = confirm_fn(command, risk, step.explanation)
            if choice == "n":
                break
            if choice == "c":
                results.append({"command": command, "return_code": -1, "stdout": "", "stderr": "Skipped (copied)"})
                continue

        result = execute_fn(
            command,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
        )
        results.append({
            "step_number": i,
            "command": command,
            "return_code": result.return_code,
            "stdout": result.stdout[:1000],
            "stderr": result.stderr[:1000],
        })
        if not result.success:
            break

    # Update success count
    all_ok = all(r.get("return_code", -1) == 0 for r in results)
    if all_ok and results:
        recipe.success_count += 1
        save_recipe(recipe)

    return results


def create_recipe_from_plan(
    name: str,
    description: str,
    steps: list,
    source_prompt: str = "",
    parameters: list[str] = None,
    parameterized_commands: list[str] = None,
    tags: list[str] = None,
) -> Recipe:
    """Create a Recipe from completed plan steps.

    Args:
        steps: List of PlanStep objects or dicts with command/explanation/is_reversible/undo_command
        parameterized_commands: If provided, use these instead of original commands (with {{param}} placeholders)
    """
    recipe_steps = []
    for i, step in enumerate(steps):
        if hasattr(step, 'command'):
            cmd = step.command
            expl = step.explanation
            rev = step.is_reversible
            undo = step.undo_command
        else:
            cmd = step.get("command", "")
            expl = step.get("explanation", "")
            rev = step.get("is_reversible", False)
            undo = step.get("undo_command", "")

        # Use parameterized command if available
        if parameterized_commands and i < len(parameterized_commands):
            cmd = parameterized_commands[i]

        recipe_steps.append(RecipeStep(
            command=cmd,
            explanation=expl,
            is_reversible=rev,
            undo_command=undo,
        ))

    return Recipe(
        name=name,
        description=description,
        steps=recipe_steps,
        parameters=parameters or [],
        tags=tags or [],
        source_prompt=source_prompt,
    )
