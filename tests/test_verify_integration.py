"""Runs the real verifier against cap-app/ when the Node toolchain is installed.

Skipped unless cap-app/node_modules/.bin/cds exists (CI installs it in the
`verify-cap` job with Node 22).
"""

import shutil

import pytest

from factory import verify

pytestmark = pytest.mark.integration

needs_cds = pytest.mark.skipif(
    not (verify.ROOT / "node_modules" / ".bin" / "cds").is_file() or not shutil.which("node"),
    reason="cap-app/node_modules not installed (npm ci in cap-app with Node >= 22)",
)


@needs_cds
def test_reference_app_verifies_end_to_end():
    report = verify.run_verification(verify.ROOT)
    assert report["ok"], report["summary"]
    smoke = next(s for s in report["steps"] if s["name"] == "smoke")
    # Empty POST must be rejected by @mandatory / handler checks, not crash.
    assert any("POST /odata/v4/gate-pass/GatePasses {} -> 400" == p for p in smoke["probes"])


@needs_cds
def test_broken_service_cds_reports_file_line(tmp_path):
    dest = tmp_path / "cap-app"
    shutil.copytree(verify.ROOT, dest, symlinks=True, ignore=shutil.ignore_patterns("node_modules"))
    (dest / "node_modules").symlink_to(verify.ROOT / "node_modules")
    (dest / "srv" / "gatepass-service.cds").write_text(
        "using my.cap as db from '../db/schema';\n"
        "service GatePassService { entity GatePasses as projection on db.Nope; }\n"
    )
    report = verify.run_verification(dest)
    compile_step = next(s for s in report["steps"] if s["name"] == "compile")
    assert report["ok"] is False and compile_step["status"] == verify.FAILED
    assert any(e.startswith("ERROR srv/gatepass-service.cds:2:") for e in compile_step["errors"])
