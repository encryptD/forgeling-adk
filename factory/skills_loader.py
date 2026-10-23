"""Load skill markdown bodies and build agent instructions that embed them.

ADK's default instruction templating treats any ``{identifier}`` in a *string*
instruction as a session-state placeholder and raises
``KeyError: Context variable not found`` when the key is missing. Skill bodies
contain CDS / JS / JSON samples with braces (``{ vehicleNo }``), so injecting
them into string instructions is unsafe.

The old loader stripped those braces, which silently corrupted code samples.
Instead, ``instruction()`` returns an ADK ``InstructionProvider``. ADK sets
``bypass_state_injection`` for providers (``LlmAgent.canonical_instruction``),
so skill text reaches the model verbatim, and only the explicitly listed
state keys are substituted by this module.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

SKILLS = Path(__file__).resolve().parent.parent / "skills"

MISSING = "(not set)"


def skill(*names: str) -> str:
    """Return the bodies of the named skills (frontmatter removed), verbatim."""
    parts = []
    for name in names:
        text = (SKILLS / name / "SKILL.md").read_text().strip()
        if text.startswith("---"):
            _, _, body = text.split("---", 2)
            text = body.strip()
        parts.append(text)
    return "\n\n".join(parts)


def _format_value(value: Any) -> str:
    if value is None:
        return MISSING
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)
    return str(value)


def render(template: str, state: Any, state_keys: tuple[str, ...]) -> str:
    """Replace ``{key}`` / ``{key?}`` for the listed keys only; leave other braces alone."""
    if not state_keys:
        return template
    pattern = re.compile(
        r"\{(" + "|".join(re.escape(k) for k in state_keys) + r")\??\}"
    )
    return pattern.sub(lambda m: _format_value(state.get(m.group(1))), template)


def instruction(template: str, *state_keys: str) -> Callable[[Any], str]:
    """Build an InstructionProvider for ``Agent(instruction=...)``.

    ``template`` may embed skill text with arbitrary braces. Only ``{key}``
    placeholders for ``state_keys`` are replaced from session state (missing
    keys render as ``(not set)`` instead of raising).
    """

    def provider(ctx) -> str:
        return render(template, ctx.state, state_keys)

    provider.__name__ = "instruction_provider"
    provider.template = template  # type: ignore[attr-defined]
    provider.state_keys = state_keys  # type: ignore[attr-defined]
    return provider
