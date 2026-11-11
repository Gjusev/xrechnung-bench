"""KoSIT validator integration (optional layer).

Runs the official KoSIT validator jar (v1.6.3 + XRechnung configuration release
2026-08-31) via subprocess. If Java or the jar is absent, validation is
SKIPPED with an explicit status — a missing validator is never reported as a
pass, and results are never faked.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_JAR = REPO_ROOT / "tools" / "validator-1.6.3-standalone.jar"
DEFAULT_SCENARIOS = REPO_ROOT / "tools" / "scenarios.xml"
VALIDATOR_JAR_URL = (
    "https://repo1.maven.org/maven2/org/kosit/validator/1.6.3/"
    "validator-1.6.3-standalone.jar"
)
CONFIG_RELEASE_URL = (
    "https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/"
    "download/v2026-08-31/xrechnung-3.0.2-validator-configuration-2026-08-31.zip"
)


def java_available() -> bool:
    return shutil.which("java") is not None


def validator_available() -> tuple[bool, str]:
    """(available, reason) — reason explains what is missing when unavailable."""
    jar = os.environ.get("XBENCH_VALIDATOR_JAR", str(DEFAULT_JAR))
    scenarios = os.environ.get("XBENCH_SCENARIOS_XML", str(DEFAULT_SCENARIOS))
    if not java_available():
        return False, "java_not_found"
    if not Path(jar).is_file():
        return False, "validator_jar_missing (%s)" % jar
    if not Path(scenarios).is_file():
        return False, "scenarios_xml_missing (%s)" % scenarios
    return True, "ok"


def build_command(xml_path: Path, jar: str, scenarios: str, repo_dir: Path) -> list[str]:
    return [
        "java", "-jar", jar,
        "-s", scenarios,
        "-r", str(repo_dir),
        "-h", str(xml_path),
    ]


def run_validator(xml_path: str | Path, workdir: str | Path | None = None,
                  timeout: int = 180) -> dict:
    """Validate one XRechnung XML file. Returns a result dict, never raises for
    an *invalid document* — only infrastructure errors raise.

    Result shape:
      {"status": "pass"|"fail"|"skipped", "reason": str|None,
       "verdict": str|None, "errors": [rule ids], "warnings": [rule ids],
       "report_path": str|None}
    """
    xml_path = Path(xml_path)
    ok, reason = validator_available()
    if not ok:
        return {"status": "skipped", "reason": reason, "verdict": None,
                "errors": [], "warnings": [], "report_path": None}

    jar = os.environ.get("XBENCH_VALIDATOR_JAR", str(DEFAULT_JAR))
    scenarios = os.environ.get("XBENCH_SCENARIOS_XML", str(DEFAULT_SCENARIOS))
    repo_dir = Path(workdir) if workdir else (xml_path.parent)
    cmd = build_command(xml_path, jar, scenarios, repo_dir)
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "skipped", "reason": "validator_timeout", "verdict": None,
                "errors": [], "warnings": [], "report_path": None}

    report = xml_path.parent / (xml_path.stem + "-report.xml")
    if not report.is_file():
        # Some validator configurations write a shared report.xml in repo_dir.
        shared = repo_dir / "report.xml"
        if shared.is_file():
            report = shared
        else:
            return {"status": "skipped", "reason": "no_report_written",
                    "verdict": None, "errors": [], "warnings": [], "report_path": None}

    parsed = parse_document_report(report)
    status = "pass" if parsed.get("verdict", "").lower() in ("valid", "pass", "true") else "fail"
    return {
        "status": status,
        "reason": None if status == "pass" else "validator_rejected",
        "verdict": parsed.get("verdict"),
        "errors": parsed.get("errors", []),
        "warnings": parsed.get("warnings", []),
        "report_path": str(report),
    }


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_document_report(path: str | Path) -> dict:
    """Parse a per-document KoSIT report (<doc>-report.xml).

    Tolerant by design: namespaces ignored, verdict read from `verdict` or
    `result` attribute, assertions collected from `assertion` or
    `failed-assert` elements. See NOTES.md — re-verify attribute names against
    real validator output on the main PC.

    Parsing uses stdlib xml.etree deliberately (no pip / third-party deps in
    the offline env): ElementTree has no DTD/entity support, so external
    entities (XXE) are rejected with ParseError rather than resolved, and the
    inputs are validator-written local reports, not untrusted web content.
    """
    tree = ET.parse(str(path))
    root = tree.getroot()
    doc_els = [e for e in root.iter() if _localname(e.tag) == "document"]
    target = doc_els[0] if doc_els else root
    verdict = target.get("verdict") or target.get("result") or ""
    errors: list[dict] = []
    warnings: list[dict] = []
    for el in root.iter():
        name = _localname(el.tag)
        if name not in ("assertion", "failed-assert"):
            continue
        entry = {
            "id": el.get("id") or "",
            "text": (el.text or "").strip() or "".join((t.text or "") for t in el),
            "flag": el.get("flag") or "",
        }
        text_lower = ((el.text or "") + entry["text"]).lower()
        is_error = (
            (el.get("type") or "").lower() in ("error", "fatal", "fatal-error")
            or (el.get("flag") or "").lower() in ("fatal", "error")
            or entry["id"].upper().startswith("BR-") and "warning" not in text_lower[:60]
            and (el.get("type") or el.get("flag") or "error") != "warning"
        )
        if is_error:
            errors.append(entry)
        else:
            warnings.append(entry)
    return {"verdict": verdict, "errors": errors, "warnings": warnings,
            "error_ids": [e["id"] for e in errors], "warning_ids": [w["id"] for w in warnings]}


def parse_svrl(path: str | Path) -> list[dict]:
    """Extract failed-assert findings from an SVRL report fragment."""
    tree = ET.parse(str(path))
    out = []
    for el in tree.getroot().iter():
        if _localname(el.tag) != "failed-assert":
            continue
        text = "".join((t.text or "") for t in el if _localname(t.tag) == "text") or (el.text or "")
        out.append({"id": el.get("id") or "", "flag": el.get("flag") or "",
                    "text": text.strip()})
    return out
