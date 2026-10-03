from datetime import datetime
from typing import Literal

import pytest
from app.agents.itinerary.artifacts import Itinerary, ItineraryItem
from app.agents.itinerary.compensation import apply_execution_command
from app.core.exceptions import PlanStateError
from app.integrations.calendar.local import LocalCalendarProvider
from app.models.calendar import CalendarAction, LocalCalendarEvent
from app.models.multi_agent import ExecutionAction, ItineraryRecord
from app.models.planning import PlanningSession
from app.models.user import LOCAL_USER_ID
from app.services.calendar.blocks import schedule_block
from app.services.calendar.idempotency import make_idempotency_key
from app.services.calendar.time import as_utc
from sqlalchemy import delete, select
from tests.conftest import CHICAGO


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 3, hour, minute, tzinfo=CHICAGO)


def _item_key(itinerary_id: str, item_type: str, source_id: str) -> str:
    return f"{itinerary_id}:{item_type}:{source_id}"


def _item(
    item_type: Literal["restaurant", "event", "travel", "buffer"],
    source_id: str,
    title: str,
    start: datetime,
    end: datetime,
) -> ItineraryItem:
    return ItineraryItem(
        item_type=item_type,
        title=title,
        start_datetime=start,
        end_datetime=end,
        location="Chicago",
        source_candidate_id=source_id,
    )


def _itinerary(itinerary_id: str, items: list[ItineraryItem]) -> Itinerary:
    return Itinerary(
        itinerary_id=itinerary_id,
        items=items,
        estimated_total_cost=40,
        start_datetime=min(item.start_datetime for item in items),
        end_datetime=max(item.end_datetime for item in items),
        valid=True,
    )


async def _plan(session, status: str) -> PlanningSession:
    plan = PlanningSession(
        user_id=LOCAL_USER_ID,
        user_request="Saturday date night",
        plan_type="itinerary",
        status=status,
        approved=False,
    )
    session.add(plan)
    await session.flush()
    return plan


def _record(plan_id, itinerary: Itinerary, *, selected: bool, rank: int) -> ItineraryRecord:
    return ItineraryRecord(
        session_id=plan_id,
        itinerary_key=itinerary.itinerary_id,
        rank_position=rank,
        estimated_total_cost=itinerary.estimated_total_cost,
        start_at=itinerary.start_datetime,
        end_at=itinerary.end_datetime,
        valid=True,
        selected=selected,
        payload=itinerary.model_dump(mode="json"),
    )


def _action(
    plan_id,
    itinerary_id: str,
    item_id: str,
    title: str,
    status: str,
    event_id: str | None = None,
    error_code: str | None = None,
) -> ExecutionAction:
    return ExecutionAction(
        session_id=plan_id,
        itinerary_key=itinerary_id,
        item_key=item_id,
        idempotency_key=make_idempotency_key(str(plan_id), item_id, "create_event"),
        title=title,
        status=status,
        calendar_event_id=event_id,
        error_code=error_code,
    )


async def _event(
    session,
    plan_id,
    title: str,
    start: datetime,
    end: datetime,
) -> LocalCalendarEvent:
    row = LocalCalendarEvent(
        user_id=LOCAL_USER_ID,
        title=title,
        start_at=as_utc(start),
        end_at=as_utc(end),
        location="Chicago",
        planning_session_id=plan_id,
    )
    session.add(row)
    await session.flush()
    return row


def _record_completed_calendar_action(session, plan_id, item_id: str, event_id) -> None:
    session.add(
        CalendarAction(
            user_id=LOCAL_USER_ID,
            session_id=plan_id,
            candidate_id=item_id,
            action_type="create_event",
            idempotency_key=make_idempotency_key(str(plan_id), item_id, "create_event"),
            status="completed",
            local_calendar_event_id=event_id,
        )
    )


def _spy_creates(monkeypatch) -> list[str]:
    created: list[str] = []
    original = LocalCalendarProvider.create_event

    async def spy(self, draft, *, idempotency_key: str, candidate_id: str):
        created.append(candidate_id)
        return await original(
            self,
            draft,
            idempotency_key=idempotency_key,
            candidate_id=candidate_id,
        )

    monkeypatch.setattr(LocalCalendarProvider, "create_event", spy)
    return created


def _spy_schedule(monkeypatch) -> list[str]:
    scheduled: list[str] = []

    async def spy(*args, **kwargs):
        scheduled.append(kwargs["item_id"])
        return await schedule_block(*args, **kwargs)

    monkeypatch.setattr("app.agents.itinerary.compensation.schedule_block", spy)
    return scheduled


async def _actions(session, plan_id) -> list[ExecutionAction]:
    return list(
        (
            await session.scalars(
                select(ExecutionAction).where(ExecutionAction.session_id == plan_id)
            )
        ).all()
    )


async def _titles(session) -> list[str]:
    rows = list((await session.scalars(select(LocalCalendarEvent))).all())
    return [row.title for row in rows]


@pytest.mark.asyncio
async def test_failed_discovery_with_no_execution_actions_does_not_write(
    session_factory, settings, monkeypatch
) -> None:
    created = _spy_creates(monkeypatch)
    async with session_factory() as session:
        plan = await _plan(session, "failed")
        dinner = _item("restaurant", "rest-1", "Dinner", _at(17), _at(18, 30))
        show = _item("event", "evt-1", "Gallery", _at(19), _at(20, 30))
        session.add(_record(plan.id, _itinerary("itin-1", [dinner, show]), selected=True, rank=0))
        await session.commit()
        with pytest.raises(PlanStateError, match="no calendar write to retry"):
            await apply_execution_command(session, settings, plan, action="retry", confirm=False)
        assert created == []
        assert await _actions(session, plan.id) == []
        assert await _titles(session) == []
        assert plan.status == "failed"


@pytest.mark.asyncio
async def test_retry_completes_only_the_incomplete_create_key(
    session_factory, settings, monkeypatch
) -> None:
    created = _spy_creates(monkeypatch)
    scheduled = _spy_schedule(monkeypatch)
    async with session_factory() as session:
        plan = await _plan(session, "partial_success")
        dinner = _item("restaurant", "rest-1", "Dinner", _at(17), _at(18, 30))
        show = _item("event", "evt-1", "Gallery", _at(19), _at(20, 30))
        extra = _item("event", "evt-extra", "Unrecorded show", _at(21), _at(22))
        travel = _item("travel", "walk-1", "Walk", _at(18, 30), _at(19))
        itinerary = _itinerary("itin-1", [dinner, travel, show, extra])
        session.add(_record(plan.id, itinerary, selected=True, rank=1))
        dinner_key = _item_key("itin-1", "restaurant", "rest-1")
        show_key = _item_key("itin-1", "event", "evt-1")
        dinner_event = await _event(session, plan.id, "Dinner", _at(17), _at(18, 30))
        _record_completed_calendar_action(session, plan.id, dinner_key, dinner_event.id)
        session.add(
            _action(plan.id, "itin-1", dinner_key, "Dinner", "completed", str(dinner_event.id))
        )
        session.add(
            _action(
                plan.id,
                "itin-1",
                show_key,
                "Gallery",
                "failed",
                error_code="calendar_write_failed",
            )
        )
        await session.commit()

        await apply_execution_command(session, settings, plan, action="retry", confirm=False)
        await session.commit()

        assert scheduled == [show_key]
        assert created == [show_key]
        actions = {row.item_key: row for row in await _actions(session, plan.id)}
        assert set(actions) == {dinner_key, show_key}
        assert actions[dinner_key].status == "completed"
        assert actions[dinner_key].calendar_event_id == str(dinner_event.id)
        assert actions[show_key].status == "completed"
        assert actions[show_key].calendar_event_id
        assert actions[show_key].error_code is None
        assert plan.status == "scheduled"
        assert plan.approved is True
        assert sorted(await _titles(session)) == ["Dinner", "Gallery"]


@pytest.mark.asyncio
async def test_retry_does_not_use_an_unselected_itinerary(
    session_factory, settings, monkeypatch
) -> None:
    created = _spy_creates(monkeypatch)
    async with session_factory() as session:
        plan = await _plan(session, "partial_success")
        ranked = _item("event", "evt-rank0", "Rank zero show", _at(19), _at(20, 30))
        selected_dinner = _item("restaurant", "rest-1", "Dinner", _at(17), _at(18, 30))
        session.add(_record(plan.id, _itinerary("itin-rank0", [ranked]), selected=False, rank=0))
        session.add(
            _record(plan.id, _itinerary("itin-selected", [selected_dinner]), selected=True, rank=1)
        )
        rank_key = _item_key("itin-rank0", "event", "evt-rank0")
        session.add(_action(plan.id, "itin-rank0", rank_key, "Rank zero show", "failed"))
        await session.commit()

        await apply_execution_command(session, settings, plan, action="retry", confirm=False)
        await session.commit()

        assert created == []
        actions = await _actions(session, plan.id)
        assert len(actions) == 1
        assert actions[0].item_key == rank_key
        assert actions[0].status == "failed"
        assert await _titles(session) == []
        assert plan.status == "partial_success"


@pytest.mark.asyncio
async def test_retry_without_a_selected_itinerary_does_not_fall_back_to_rank_zero(
    session_factory, settings, monkeypatch
) -> None:
    created = _spy_creates(monkeypatch)
    async with session_factory() as session:
        plan = await _plan(session, "failed")
        ranked = _item("restaurant", "rest-1", "Dinner", _at(17), _at(18, 30))
        session.add(_record(plan.id, _itinerary("itin-rank0", [ranked]), selected=False, rank=0))
        item_id = _item_key("itin-rank0", "restaurant", "rest-1")
        session.add(_action(plan.id, "itin-rank0", item_id, "Dinner", "failed"))
        await session.commit()

        with pytest.raises(PlanStateError, match="no itinerary to schedule"):
            await apply_execution_command(session, settings, plan, action="retry", confirm=False)

        assert created == []
        actions = await _actions(session, plan.id)
        assert len(actions) == 1
        assert actions[0].status == "failed"
        assert await _titles(session) == []
        assert plan.status == "failed"


@pytest.mark.asyncio
async def test_schedule_conflict_leaves_the_create_key_incomplete(
    session_factory, settings, monkeypatch
) -> None:
    created = _spy_creates(monkeypatch)
    scheduled = _spy_schedule(monkeypatch)
    async with session_factory() as session:
        plan = await _plan(session, "partial_success")
        dinner = _item("restaurant", "rest-1", "Dinner", _at(17), _at(18, 30))
        show = _item("event", "evt-1", "Gallery", _at(19), _at(20, 30))
        itinerary = _itinerary("itin-1", [dinner, show])
        session.add(_record(plan.id, itinerary, selected=True, rank=0))
        dinner_key = _item_key("itin-1", "restaurant", "rest-1")
        show_key = _item_key("itin-1", "event", "evt-1")
        dinner_event = await _event(session, plan.id, "Dinner", _at(17), _at(18, 30))
        _record_completed_calendar_action(session, plan.id, dinner_key, dinner_event.id)
        session.add(
            _action(plan.id, "itin-1", dinner_key, "Dinner", "completed", str(dinner_event.id))
        )
        show_action = _action(plan.id, "itin-1", show_key, "Gallery", "failed")
        session.add(show_action)
        await _event(session, plan.id, "Existing appointment", _at(19, 15), _at(19, 45))
        await session.commit()
        show_idempotency = show_action.idempotency_key

        await apply_execution_command(session, settings, plan, action="retry", confirm=False)
        await session.commit()

        actions = {row.item_key: row for row in await _actions(session, plan.id)}
        assert scheduled == [show_key]
        assert created == []
        assert actions[show_key].status == "failed"
        assert actions[show_key].error_code == "schedule_conflict"
        assert actions[show_key].idempotency_key == show_idempotency
        assert actions[dinner_key].status == "completed"
        assert actions[dinner_key].calendar_event_id == str(dinner_event.id)
        assert plan.status == "partial_success"
        assert "Gallery" not in await _titles(session)

        await session.execute(
            delete(LocalCalendarEvent).where(LocalCalendarEvent.title == "Existing appointment")
        )
        await session.commit()
        stored = await session.get(PlanningSession, plan.id)
        assert stored is not None
        await apply_execution_command(session, settings, stored, action="retry", confirm=False)
        await session.commit()

        actions = {row.item_key: row for row in await _actions(session, stored.id)}
        assert scheduled == [show_key, show_key]
        assert created == [show_key]
        assert actions[show_key].status == "completed"
        assert actions[show_key].error_code is None
        assert actions[dinner_key].status == "completed"
        assert actions[dinner_key].calendar_event_id == str(dinner_event.id)
        assert stored.status == "scheduled"
        assert sorted(await _titles(session)) == ["Dinner", "Gallery"]


@pytest.mark.asyncio
async def test_cancel_without_confirm_raises_and_deletes_nothing(
    session_factory, settings, monkeypatch
) -> None:
    created = _spy_creates(monkeypatch)
    async with session_factory() as session:
        plan = await _plan(session, "partial_success")
        dinner = _item("restaurant", "rest-1", "Dinner", _at(17), _at(18, 30))
        session.add(_record(plan.id, _itinerary("itin-1", [dinner]), selected=True, rank=0))
        dinner_key = _item_key("itin-1", "restaurant", "rest-1")
        dinner_event = await _event(session, plan.id, "Dinner", _at(17), _at(18, 30))
        session.add(
            _action(plan.id, "itin-1", dinner_key, "Dinner", "completed", str(dinner_event.id))
        )
        await session.commit()

        with pytest.raises(PlanStateError, match="Confirm before removing"):
            await apply_execution_command(
                session, settings, plan, action="cancel_created", confirm=False
            )

        actions = await _actions(session, plan.id)
        assert created == []
        assert len(actions) == 1
        assert actions[0].status == "completed"
        assert actions[0].calendar_event_id == str(dinner_event.id)
        assert await _titles(session) == ["Dinner"]
