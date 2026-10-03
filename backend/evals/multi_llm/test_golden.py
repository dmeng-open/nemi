"""Golden checks. Default pytest skips them.

Missing-date behavior, the shared replan cap, invalid-output retry, and fail-closed
retries stay in the unit tests. This module does not call OpenAI while those
variables are unset, and it does not invent a score when the live port is absent.
"""

import pytest
from evals.multi_llm.checks import (
    dinner_and_activity_failures,
    failed_branch_failures,
    hard_constraint_failures,
    write_count_failures,
)
from evals.multi_llm.fixtures import CRITIC_REPLAN, DATE_NIGHT, FAILED_BRANCH
from evals.multi_llm.gate import NOT_RUN_REASON, model_evals_enabled
from evals.multi_llm.runner import run_baseline, run_live

pytestmark = pytest.mark.skipif(not model_evals_enabled(), reason=NOT_RUN_REASON)


def _require_live_port():
    if not model_evals_enabled():
        pytest.skip(NOT_RUN_REASON)
    from app.agents.itinerary.structured_output import OpenAIStructuredOutput
    from app.core.config import Settings

    settings = Settings()
    if not settings.openai_configured:
        pytest.skip(NOT_RUN_REASON)
    return OpenAIStructuredOutput(settings)


async def _compare(case, check) -> None:
    port = _require_live_port()
    baseline = await run_baseline(case)
    live = await run_live(case, port)
    baseline_failures = check(baseline)
    live_failures = check(live)
    assert baseline_failures == [], baseline_failures
    assert live_failures == [], live_failures


async def test_date_night_itinerary_contains_dinner_and_activity() -> None:
    await _compare(DATE_NIGHT, dinner_and_activity_failures)


async def test_date_night_has_no_hard_constraint_violation() -> None:
    await _compare(DATE_NIGHT, hard_constraint_failures)


async def test_critic_replan_reopens_only_the_failed_branch() -> None:
    await _compare(
        CRITIC_REPLAN,
        lambda outcome: failed_branch_failures(outcome, failed_branch=FAILED_BRANCH),
    )


async def test_one_approve_writes_two_calendar_events() -> None:
    await _compare(DATE_NIGHT, write_count_failures)
