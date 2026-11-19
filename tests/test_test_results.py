# SPDX-License-Identifier: Apache-2.0
"""Exercise reporting failures without sending any GitHub requests."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "test_results", Path(__file__).parents[1] / "tools/test_results.py"
)
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
SHA = "4bb3fdff151f1cfbde923ccc0f2d7c8516ee9b98"
URL = "https://github.com/example/project/runs/123"
PASS = '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite>'
FAIL = '<testsuite tests="1" failures="1"><testcase name="bad"><failure message="fixture"/></testcase></testsuite>'


class Publisher:
    def __init__(self, mode="success"):
        self.mode = mode
        self.bodies = []

    def create_check_run(self, body):
        self.bodies.append(body)
        if self.mode == "403":
            raise reporter.CheckApiError(403, "create")
        if self.mode == "unfinished":
            return {"id": 123, "status": "in_progress"}
        result = {**body, "html_url": URL}
        if self.mode == "wrong-conclusion":
            result["conclusion"] = "failure"
        if self.mode == "missing-url":
            result.pop("html_url")
        return result

    def update_check_run(self, check_id, body):
        raise reporter.CheckApiError(404, "update")


def evaluate(tmp_path, xml=PASS, api=None, publish=True, sha=SHA):
    path = tmp_path / "tests.xml"
    if xml is not None:
        path.write_text(xml)
    return reporter.evaluate(
        "tests.xml",
        root=tmp_path,
        name="fixture",
        head_sha=sha,
        api=api,
        publish=publish,
        completed_at="2026-11-19T00:00:00Z",
    )


def test_passing_publication_has_cases_and_link(tmp_path):
    api = Publisher()
    result = evaluate(tmp_path, api=api)
    assert result["exit_code"] == 0
    assert result["check"]["html_url"] == URL
    assert "PASS" in api.bodies[0]["output"]["summary"]


@pytest.mark.parametrize("mode", ["403", "unfinished", "wrong-conclusion", "missing-url"])
def test_publication_failure_fails_verification(tmp_path, mode):
    result = evaluate(tmp_path, api=Publisher(mode))
    assert result["exit_code"] == 1
    assert "publication did not complete" in result["summary"]


@pytest.mark.parametrize("sha", [SHA, "invalid"])
def test_missing_publication_prerequisites_fail(tmp_path, sha):
    assert evaluate(tmp_path, sha=sha)["exit_code"] == 1


def test_restricted_fork_explicitly_disables_publication(tmp_path):
    result = evaluate(tmp_path, publish=False)
    assert result["exit_code"] == 0
    assert "disabled explicitly" in result["summary"]
    assert evaluate(tmp_path, xml=FAIL, publish=False)["exit_code"] == 1


@pytest.mark.parametrize(
    "xml",
    [
        None,
        "<testsuite",
        "<testsuite tests='0'/>",
        '<testsuite tests="2"><testcase name="one"/></testsuite>',
        '<testsuite tests="1" failures="1"><testcase name="one"/></testsuite>',
        '<testsuite tests="1" errors="1"><testcase name="one"/></testsuite>',
        '<testsuite tests="1" skipped="1"><testcase name="one"/></testsuite>',
        '<testsuite tests="invalid"><testcase name="one"/></testsuite>',
        '<testsuite><testcase name="one"/></testsuite>',
        '<testsuites tests="2">' + PASS + "</testsuites>",
        '<unrelated><testcase name="one"/></unrelated>',
    ],
)
def test_incomplete_or_unreadable_evidence_fails(tmp_path, xml):
    api = Publisher()
    result = evaluate(tmp_path, xml=xml, api=api)
    assert result["exit_code"] == 1
    assert not api.bodies or api.bodies[0]["conclusion"] == "failure"


def test_nested_suite_totals_are_checked(tmp_path):
    xml = '<testsuites tests="1"><testsuite tests="1">' + PASS + "</testsuite></testsuites>"
    assert evaluate(tmp_path, xml=xml, api=Publisher())["exit_code"] == 0
    xml = xml.replace('<testsuite tests="1">', '<testsuite tests="2">', 1)
    assert evaluate(tmp_path, xml=xml, api=Publisher())["exit_code"] == 1


def test_failed_test_stays_failed_and_is_published(tmp_path):
    api = Publisher()
    result = evaluate(tmp_path, xml=FAIL, api=api)
    assert result["exit_code"] == 1
    assert result["failed"] == 1
    assert api.bodies[0]["conclusion"] == "failure"
    assert "fixture" in api.bodies[0]["output"]["summary"]


def test_cli_writes_summary_counts_and_check_url(tmp_path, monkeypatch):
    (tmp_path / "tests.xml").write_text(PASS)
    monkeypatch.setenv("HEAD_SHA", SHA)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    monkeypatch.setattr(reporter, "client_from_env", lambda: Publisher())
    assert reporter.main(["--name", "fixture", "--path", "tests.xml", "--root", str(tmp_path)]) == 0
    assert f"url_html={URL}" in (tmp_path / "outputs").read_text()
    assert "passed=1" in (tmp_path / "outputs").read_text()
    assert "passed 1" in (tmp_path / "summary").read_text()
