"""Regression tests for scripts/verify_fiori_skill.py validators (no LLM)."""

import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_fiori_skill", ROOT / "scripts" / "verify_fiori_skill.py")
vfs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vfs)


@pytest.fixture
def app_copy(tmp_path, monkeypatch):
    dest = tmp_path / "cap-app"
    shutil.copytree(ROOT / "cap-app", dest, ignore=shutil.ignore_patterns("node_modules", "gen"))
    monkeypatch.setattr(vfs, "CAP_APP", dest)
    return dest


def test_committed_reference_app_passes(app_copy):
    # Previously failed: index.html was required to contain ComponentSupport /
    # AppComponent, but the boilerplate skill mandates ComponentContainer.
    assert vfs.validate_generated_app() == []


def test_component_must_extend_fe_app_component(app_copy):
    comp = app_copy / "app/gatepass/webapp/Component.js"
    comp.write_text(comp.read_text().replace("sap/fe/core/AppComponent", "sap/ui/core/UIComponent"))
    assert any("AppComponent" in e for e in vfs.validate_generated_app())


def test_index_without_bootstrap_fails(app_copy):
    idx = app_copy / "app/gatepass/webapp/index.html"
    idx.write_text(idx.read_text().replace("ComponentContainer", "Nothing"))
    assert any("ComponentContainer" in e for e in vfs.validate_generated_app())


@pytest.mark.parametrize(
    "service, expected",
    [
        ("using my.cap as db from '../db/schema';", None),
        ("using { my.cap.GatePass } from '../db/schema';", None),
        ("using other.ns as db from '../db/schema';", "using=other.ns"),
        ("using { other.GatePass } from '../db/schema';", "using=other"),
        ("using { GatePass } from '../db/schema';", "using=(none)"),
    ],
)
def test_namespace_mismatch(service, expected):
    err = vfs.namespace_mismatch("namespace my.cap;\nentity GatePass {}", service)
    if expected is None:
        assert err is None
    else:
        assert err and expected in err


def test_namespace_mismatch_detected_end_to_end(app_copy):
    svc = app_copy / "srv/gatepass-service.cds"
    svc.write_text(svc.read_text().replace("using my.cap as db", "using wrong.ns as db"))
    assert any("namespace mismatch" in e for e in vfs.validate_generated_app())


def test_prompt_no_longer_asks_for_i18n_files():
    assert "i18n/i18n.properties" not in vfs.PROMPT
    assert "no i18n" in vfs.PROMPT
