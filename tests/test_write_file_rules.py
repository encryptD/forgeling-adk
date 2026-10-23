"""_normalize_rel_path and _validate_fe_content (pure functions, no I/O)."""

import json

import pytest

from factory import tools
from factory.tools import (
    ANNOTATIONS_TEMPLATE,
    CAP_PACKAGE_TEMPLATE,
    INDEX_HTML_TEMPLATE,
    MANIFEST_TEMPLATE,
    _normalize_rel_path,
    _sanitize_content,
    _validate_fe_content,
)


@pytest.mark.parametrize(
    "given, expected",
    [
        ("db/schema.cds", "db/schema.cds"),
        ("/db/schema.cds", "db/schema.cds"),
        ("./srv/gatepass-service.js", "srv/gatepass-service.js"),
        ("cap-app/db/schema.cds", "db/schema.cds"),
        ("cap-app/cap-app/srv/x.cds", "srv/x.cds"),
        ("CAP-APP/db/schema.cds", "db/schema.cds"),
        ("srv\\gatepass-service.cds", "srv/gatepass-service.cds"),
        ("srv/gate-pass-service.js", "srv/gatepass-service.js"),
        ("app/gatepass-fiori/webapp/index.html", "app/gatepass/webapp/index.html"),
        ("app/gatepass-list-report/ui5.yaml", "app/gatepass/ui5.yaml"),
        ("app/gatepass/webapp/annotations.cds", "app/gatepass/annotations.cds"),
    ],
)
def test_normalize_rel_path(given, expected):
    assert _normalize_rel_path(given) == expected


@pytest.mark.parametrize("bad", ["", ".", "cap-app", "cap-app/", "../etc/passwd", "srv/../../x"])
def test_normalize_rel_path_rejects(bad):
    with pytest.raises(ValueError):
        _normalize_rel_path(bad)


def test_templates_pass_their_own_rules():
    for rel, content in [
        ("app/gatepass/annotations.cds", ANNOTATIONS_TEMPLATE),
        ("app/gatepass/webapp/index.html", INDEX_HTML_TEMPLATE),
        ("package.json", CAP_PACKAGE_TEMPLATE),
        ("srv/gatepass-service.cds", tools.SERVICE_CDS_TEMPLATE),
    ]:
        assert _validate_fe_content(rel, content) is None, rel
    manifest = _sanitize_content("app/gatepass/webapp/manifest.json", MANIFEST_TEMPLATE)
    assert _validate_fe_content("app/gatepass/webapp/manifest.json", manifest) is None
    json.loads(manifest)


def test_empty_content_rejected():
    assert "empty" in _validate_fe_content("db/schema.cds", "   ")


def test_inline_mandatory_in_projection_rejected():
    bad = (
        "using my.cap as db from '../db/schema';\n"
        "service S { entity GatePasses as projection on db.GatePass { *, plant @mandatory; } }\n"
    )
    assert "@mandatory" in _validate_fe_content("srv/gatepass-service.cds", bad)


def test_absolute_service_path_rejected_and_sanitized():
    bad = "service GatePassService @(path: '/gate-pass') { }"
    assert "relative" in _validate_fe_content("srv/gatepass-service.cds", bad)
    fixed = _sanitize_content("srv/gatepass-service.cds", bad)
    assert "path: 'gate-pass'" in fixed


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda s: s.replace("1.145.0", "1.136.0"), "1.136.0"),
        (lambda s: s.replace("data-sap-ui-resourceroots", "data-x"), "resourceroots"),
        (lambda s: s.replace("ComponentContainer", "Nothing"), "ComponentContainer"),
        (lambda s: s.replace("componentPreload", "preload"), "componentPreload"),
    ],
)
def test_index_html_rules(mutate, needle):
    err = _validate_fe_content("app/gatepass/webapp/index.html", mutate(INDEX_HTML_TEMPLATE))
    assert err and needle in err


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda s: s.replace("/odata/v4/gate-pass/", "/gate-pass/x"), "/odata/v4/gate-pass/"),
        (lambda s: s.replace("ObjectPage", "Detail"), "ObjectPage"),
        (lambda s: s.replace('"Gate Passes"', '"{{appTitle}}"'), "i18n"),
    ],
)
def test_manifest_rules(mutate, needle):
    content = mutate(_sanitize_content("app/gatepass/webapp/manifest.json", MANIFEST_TEMPLATE))
    err = _validate_fe_content("app/gatepass/webapp/manifest.json", content)
    assert err and needle in err


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda s: s.replace("UI.SelectionFields", "UI.Other"), "SelectionFields"),
        (lambda s: s.replace("gatepass-service", "gate-pass-service"), "gate-pass-service"),
        (lambda s: s[:60], "too short"),
    ],
)
def test_annotations_rules(mutate, needle):
    err = _validate_fe_content("app/gatepass/annotations.cds", mutate(ANNOTATIONS_TEMPLATE))
    assert err and needle in err


def test_cap_package_sqlite_v1_with_cds10_rejected():
    pkg = json.loads(CAP_PACKAGE_TEMPLATE)
    pkg["dependencies"]["@cap-js/sqlite"] = "^1"
    err = _validate_fe_content("package.json", json.dumps(pkg))
    assert err and "^3" in err


def test_cap_package_invalid_json_rejected():
    assert "invalid JSON" in _validate_fe_content("package.json", "{nope")


def test_app_package_must_be_ui_only():
    err = _validate_fe_content(
        "app/gatepass/package.json", '{"dependencies": {"@sap/cds": "^10"}}'
    )
    assert err and "UI-only" in err


def test_escaped_yaml_rejected():
    assert "escaped" in _validate_fe_content("app/gatepass/ui5.yaml", "a: 1\\nb: 2\\nc: 3\\nd: 4")


def test_write_file_refuses_escape_and_outside(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ROOT", tmp_path)
    assert tools.write_file("../x.cds", "entity X {}")["ok"] is False
    res = tools.write_file("cap-app/db/schema.cds", "namespace a;\nentity X { key ID : UUID; }\n")
    assert res["ok"] and res["rel"] == "db/schema.cds"
    assert (tmp_path / "db" / "schema.cds").is_file()
    assert not (tmp_path / "cap-app").exists()
