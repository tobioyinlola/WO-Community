"""The production settings must pass `check --deploy` with throwaway values.

CI runs `scripts/deploy_check.py` too, but only after a push. Adding a required production setting
without a placeholder in that script used to be found there; this test finds it in the normal test
run instead, before anything is pushed.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# Only what the interpreter needs: the script fills in the rest, and the test run's own settings
# (which the script would otherwise keep) must not leak in.
BASIC_ENV = {
    k: v for k, v in os.environ.items() if k in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME"}
}


def test_production_settings_pass_the_deployment_check():
    result = subprocess.run(  # noqa: S603 - our own script, no user input
        [sys.executable, "scripts/deploy_check.py"],
        cwd=ROOT,
        env=BASIC_ENV,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        "Production settings need a setting that scripts/deploy_check.py does not fill in.\n"
        f"{result.stdout}\n{result.stderr}"
    )
