"""Skill text must reach the model verbatim; only listed state keys are filled."""

import asyncio
from types import SimpleNamespace

import pytest

from factory import agent as factory_agent
from factory.skills_loader import MISSING, SKILLS, instruction, render, skill


def test_skill_keeps_braces_and_strips_frontmatter():
    text = skill("sap-fiori-boilerplate")
    assert not text.startswith("---")
    assert "{ $Type: 'UI.DataField', Value: number }" in text  # braces preserved


def test_render_only_touches_listed_keys():
    tpl = "A {spec_pack} B { vehicleNo } C {work_item?} D {other} E {{x}}"
    out = render(tpl, {"spec_pack": "SP", "other": "NO"}, ("spec_pack", "work_item"))
    assert out == f"A SP B {{ vehicleNo }} C {MISSING} D {{other}} E {{{{x}}}}"


def test_render_formats_dicts_as_json():
    out = render("{gate_result}", {"gate_result": {"approved": True}}, ("gate_result",))
    assert '"approved": true' in out


def test_provider_bypasses_adk_state_injection():
    """ADK only injects state into *string* instructions; providers bypass it."""
    impl = factory_agent.implement
    assert callable(impl.instruction)
    ctx = SimpleNamespace(state={"spec_pack": "SPEC", "gate_result": None, "verify_result": None})
    text, bypass = asyncio.run(impl.canonical_instruction(ctx))
    assert bypass is True
    assert "SPEC" in text and MISSING in text
    assert "{ $Type: 'UI.DataField'" in text


@pytest.mark.parametrize("path", sorted(SKILLS.glob("*/SKILL.md")))
def test_skills_do_not_contain_state_placeholders(path):
    keys = ("work_item", "spec_pack", "gate_result", "change", "verify_result",
            "review_note", "mvp_brief", "mvp_app")
    body = path.read_text()
    for k in keys:
        assert "{" + k + "}" not in body and "{" + k + "?}" not in body
