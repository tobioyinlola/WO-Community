"""Job kinds owned by the model layer."""

from typing import Any

from apps.toolkit.ai import runner
from apps.toolkit.jobs import services as jobs


def selfcheck(ctx: jobs.JobContext) -> dict[str, Any]:
    """Asks the model for one trivial structured answer: proves the whole path works."""
    ctx.progress(10, "Checking the assistant")
    answer = runner.structured(
        prompt_id="system.selfcheck",
        variables={"word": str(ctx.payload.get("word", "ping"))},
        owner_id=ctx.owner_id,
        venture=ctx.venture,
        job=ctx.job,
    )
    ctx.progress(90, "Done")
    return {"type": "selfcheck", "ok": bool(answer["ok"]), "echo": answer["echo"]}


def register() -> None:
    jobs.register("system.selfcheck", selfcheck)
