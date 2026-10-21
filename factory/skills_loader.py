"""Load skill markdown bodies for injection into agent instructions.

ADK treats `{name}` in instructions as session context placeholders.
Skill samples (JS destructuring, etc.) must not use bare `{ident}` or the
run fails with KeyError: Context variable not found: `ident`.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"

# `{ vehicleNo }` or `{vehicleNo}` — single identifier only (optional spaces).
_ADK_IDENT_BRACE = re.compile(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}")


def _neutralize_adk_context_braces(text: str) -> str:
    """Rewrite single-ident brace groups so ADK does not expand them.

    Example: `const { vehicleNo } = …` -> `const vehicleNo = … (from req.data)`
    is handled in skill source; this is a safety net that turns residual
    `{foo}` into `foo` (no braces).
    """

    return _ADK_IDENT_BRACE.sub(r"\1", text)


def skill(*names: str) -> str:
    parts = []
    for name in names:
        text = (SKILLS / name / "SKILL.md").read_text().strip()
        if text.startswith("---"):
            _, _, body = text.split("---", 2)
            text = body.strip()
        text = _neutralize_adk_context_braces(text)
        parts.append(text)
    return "\n\n".join(parts)
