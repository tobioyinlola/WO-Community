import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.toolkit.admin_api import evaluation


def test_the_evaluation_set_passes():
    report = evaluation.run()
    failed = [(c.name, c.detail) for c in report.checks if not c.passed]
    assert not failed, failed
    assert len(report.rows) == 20 and len(report.checks) > 200


def test_the_ventures_really_differ():
    ventures = evaluation.ventures()
    assert len({v["revenue_models"][0] for v in ventures}) == 6
    assert len({v["country"] for v in ventures}) == 5
    assert any("traction" in v for v in ventures) and any("traction" not in v for v in ventures)


def test_the_command_reports_and_fails_loudly(monkeypatch):
    out = StringIO()
    call_command("toolkit_evaluate", "--json", stdout=out)
    body = json.loads(out.getvalue())
    assert body["ok"] is True and body["failed"] == []

    broken = evaluation.Report()
    broken.add("something that must hold", False, "it did not")
    monkeypatch.setattr(evaluation, "run", lambda: broken)
    with pytest.raises(CommandError):
        call_command("toolkit_evaluate", stdout=StringIO())
