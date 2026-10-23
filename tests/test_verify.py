"""Verifier parsing and graceful degradation (no node/npm required)."""

import json

import pytest

from factory import verify
from factory.verify import (
    FAILED,
    PASSED,
    SKIPPED,
    format_message,
    parse_cds_messages,
    parse_entity_sets,
    parse_service_paths,
    run_verification,
    strip_ansi,
)

CDS_OUTPUT = (
    "[\x1b[91m\x1b[1mERROR\x1b[0m] srv/gatepass-service.cds:1:25-39: Mismatched ‹Identifier›, expecting ‹String›\n"
    "[ERROR] srv/gatepass-service.cds:2:42-46: Artifact “my.cap.Nope” has not been found (in entity:“X.A”/query:1)\n"
    "[\x1b[38;2;255;140;0m\x1b[1mWARNING\x1b[0m] app/gatepass/annotations.cds:3:18-28: Artifact “GatePassService.GatePasses” has not been found\n"
    "[ERROR] CDS compilation failed without location\n"
    "some unrelated line\n"
)


def test_strip_ansi():
    assert strip_ansi("\x1b[91mERROR\x1b[0m") == "ERROR"


def test_parse_cds_messages():
    msgs = parse_cds_messages(CDS_OUTPUT)
    assert [m["severity"] for m in msgs] == ["error", "error", "warning", "error"]
    first = msgs[0]
    assert first["file"] == "srv/gatepass-service.cds"
    assert (first["line"], first["col"]) == (1, 25)
    assert first["message"].startswith("Mismatched")
    assert msgs[3]["file"] is None and msgs[3]["line"] is None


def test_format_message():
    m = parse_cds_messages(CDS_OUTPUT)[1]
    assert format_message(m).startswith("ERROR srv/gatepass-service.cds:2:42: Artifact")
    assert format_message(parse_cds_messages(CDS_OUTPUT)[3]) == (
        "ERROR: CDS compilation failed without location"
    )


def test_parse_service_paths_and_entity_sets():
    log = (
        "[cds] - serving GatePassService {\n  at: [ \x1b[32m'/odata/v4/gate-pass'\x1b[39m ],\n"
        "[cds] - serving Other {\n  at: [ '/odata/v4/other' ],\n"
    )
    assert parse_service_paths(log) == ["/odata/v4/gate-pass", "/odata/v4/other"]
    xml = '<EntityContainer><EntitySet Name="GatePasses" EntityType="X"/><EntitySet Name="Plants"/></EntityContainer>'
    assert parse_entity_sets(xml) == ["GatePasses", "Plants"]


@pytest.fixture
def project(tmp_path):
    (tmp_path / "db").mkdir()
    (tmp_path / "srv").mkdir()
    (tmp_path / "package.json").write_text(json.dumps({"name": "x", "dependencies": {}}))
    (tmp_path / "db" / "schema.cds").write_text("namespace a;\nentity X { key ID : UUID; }\n")
    return tmp_path


def test_missing_toolchain_degrades_gracefully(project):
    report = run_verification(project)
    assert report["ok"] is False and report["toolchain_ok"] is False
    steps = {s["name"]: s for s in report["steps"]}
    assert steps["compile"]["status"] == SKIPPED
    assert "npm ci" in steps["compile"]["reason"]
    assert steps["build"]["status"] == SKIPPED and steps["smoke"]["status"] == SKIPPED
    assert "npm" in report["hint"]
    assert "[SKIPPED] compile" in report["summary"]


def test_missing_project_dir(tmp_path):
    report = run_verification(tmp_path / "nope")
    assert report["ok"] is False and report["toolchain_ok"] is False


def test_static_flags_bad_json_and_yaml(project, monkeypatch):
    monkeypatch.setattr(verify, "_node_bin", lambda: None)
    (project / "app" / "gatepass" / "webapp").mkdir(parents=True)
    (project / "app" / "gatepass" / "webapp" / "manifest.json").write_text("{bad json")
    (project / "app" / "gatepass" / "ui5.yaml").write_text("a: [1, 2\n")
    step = verify.check_static(project)
    assert step["status"] == FAILED
    text = "\n".join(step["errors"])
    assert "invalid JSON" in text and "invalid YAML" in text


def test_compile_failure_is_parsed_and_later_steps_skipped(project, monkeypatch):
    monkeypatch.setattr(verify, "_toolchain_reason", lambda root: None)
    monkeypatch.setattr(verify, "_cds_bin", lambda root: project / "cds")
    monkeypatch.setattr(verify, "_node_bin", lambda: None)
    monkeypatch.setattr(verify, "_run", lambda cmd, cwd, timeout: (1, CDS_OUTPUT))
    report = run_verification(project)
    steps = {s["name"]: s for s in report["steps"]}
    assert steps["compile"]["status"] == FAILED
    assert any("srv/gatepass-service.cds:2:42" in e for e in steps["compile"]["errors"])
    assert steps["compile"]["warnings"]
    assert steps["build"]["status"] == SKIPPED
    assert steps["build"]["reason"] == "earlier step failed"
    assert report["ok"] is False and report["toolchain_ok"] is True


def test_compile_requires_ui_annotations_when_app_has_them(project, monkeypatch):
    monkeypatch.setattr(verify, "_toolchain_reason", lambda root: None)
    monkeypatch.setattr(verify, "_cds_bin", lambda root: project / "cds")
    monkeypatch.setattr(verify, "_run", lambda cmd, cwd, timeout: (0, "<edmx/>"))
    (project / "app" / "x").mkdir(parents=True)
    (project / "app" / "x" / "annotations.cds").write_text("annotate X with @UI.LineItem: [];")
    step = verify.check_compile(project)
    assert step["status"] == FAILED
    assert any("UI.SelectionFields" in e for e in step["errors"])
    assert verify.check_compile(project, require_ui=False)["status"] == PASSED


def test_all_green(project, monkeypatch):
    monkeypatch.setattr(verify, "_toolchain_reason", lambda root: None)
    monkeypatch.setattr(verify, "_cds_bin", lambda root: project / "cds")
    monkeypatch.setattr(verify, "_node_bin", lambda: None)
    monkeypatch.setattr(verify, "_run", lambda cmd, cwd, timeout: (0, "ok"))
    monkeypatch.setattr(verify, "check_smoke", lambda root: verify._step("smoke", PASSED))
    report = run_verification(project)
    assert report["ok"] is True and report["hint"] is None
    assert [s["status"] for s in report["steps"]] == [PASSED] * 4
