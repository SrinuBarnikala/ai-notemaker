"""Deterministic concurrency tests: requests are interleaved with events (never with sleeps) so the
exact ordering is controlled, and each assertion is about observable journey state."""
import asyncio

import pytest

from backend.app.db.session import SessionLocal
from backend.app.discovery.locks import JourneyLocks, discovery_locks
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.models.journey import LearningJourney
from discovery_helpers import Gate, opening, turn, finding

Q1 = "Why do you think we needed a way to adjust weights automatically?"
Q2 = "What would you like to be able to do with this idea?"
GROUNDED = {
    "understanding": finding("Knows the forward pass", "demonstrated", "the forward pass"),
    "intent": finding("Wants concepts", "stated", "concepts"),
}


@pytest.fixture
async def scripted_async(scripted):
    """The shared scripted provider plus a check that no lock entries leak between tests."""
    assert discovery_locks.active() == 0
    yield scripted
    assert discovery_locks.active() == 0, "a journey lock leaked"


async def new_journey(client, topic="How does backpropagation work?"):
    return (await client.post("/journeys", json={"topic": topic})).json()["id"]


async def wait_until(predicate, timeout=10.0):
    """Wait for an explicit condition. Real time, not event-loop turns: FastAPI resolves sync dependencies
    (the DB session) in a thread pool, so a request needs wall-clock time to reach the lock."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition was never reached")
        await asyncio.sleep(0.005)


def rows(journey_id):
    db = SessionLocal()
    try:
        return [(r.question_index, r.learner_answer is not None) for r in
                db.query(DiscoveryInteraction).filter_by(journey_id=journey_id).order_by(DiscoveryInteraction.question_index)]
    finally:
        db.close()


def status(journey_id):
    db = SessionLocal()
    try:
        return db.query(LearningJourney).filter_by(id=journey_id).one().status
    finally:
        db.close()


# ---------------------------------------------------------------------------
# The lock itself
# ---------------------------------------------------------------------------

async def test_lock_serializes_per_journey_but_not_across_journeys_and_cleans_up():
    locks = JourneyLocks()
    order = []
    release_a = asyncio.Event()

    async def worker(name, journey, wait_for=None):
        async with locks.hold(journey):
            order.append(f"{name}-in")
            if wait_for is not None:
                await wait_for.wait()
            order.append(f"{name}-out")

    a = asyncio.create_task(worker("a", "j1", release_a))
    await wait_until(lambda: "a-in" in order)
    b = asyncio.create_task(worker("b", "j1"))          # same journey: must wait
    c = asyncio.create_task(worker("c", "j2"))          # other journey: must not wait
    await wait_until(lambda: "c-out" in order)
    assert locks.holders("j1") == 2 and "b-in" not in order
    release_a.set()
    await asyncio.gather(a, b, c)
    assert order.index("a-out") < order.index("b-in")
    assert locks.active() == 0 and locks.holders("j1") == 0


async def test_lock_is_released_and_cleaned_up_when_the_holder_fails_or_is_cancelled():
    locks = JourneyLocks()

    async def fail():
        async with locks.hold("j"):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await fail()
    assert locks.active() == 0

    never = asyncio.Event()

    async def hang():
        async with locks.hold("j"):
            await never.wait()

    holder = asyncio.create_task(hang())
    await wait_until(lambda: locks.holders("j") == 1)
    waiter = asyncio.create_task(fail())
    await wait_until(lambda: locks.holders("j") == 2)
    waiter.cancel()                                      # a waiter that gives up must not wedge the lock
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert locks.holders("j") == 1
    holder.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder
    assert locks.active() == 0
    async with locks.hold("j"):                           # still usable afterwards
        pass


# ---------------------------------------------------------------------------
# D2: simultaneous starts
# ---------------------------------------------------------------------------

async def test_simultaneous_starts_create_exactly_one_first_question(async_client, scripted_async):
    gate = Gate(opening(Q1))
    scripted_async.push(gate, opening("A different opening question that must never be used?"))
    journey_id = await new_journey(async_client)

    first = asyncio.create_task(async_client.post(f"/journeys/{journey_id}/discovery/start"))
    await asyncio.wait_for(gate.entered.wait(), 5)
    second = asyncio.create_task(async_client.post(f"/journeys/{journey_id}/discovery/start"))
    await wait_until(lambda: discovery_locks.holders(journey_id) == 2)
    assert scripted_async.calls == 1                       # the second request is waiting, not calling the model
    gate.release.set()
    r1, r2 = await asyncio.gather(first, second)

    assert r1.status_code == r2.status_code == 200
    assert r1.json()["question_text"] == r2.json()["question_text"] == Q1
    assert scripted_async.calls == 1                       # and it never made its own model call
    assert rows(journey_id) == [(1, False)]
    assert status(journey_id) == "discovery"


# ---------------------------------------------------------------------------
# D1: a reload during an in-flight answer
# ---------------------------------------------------------------------------

async def _start(client, scripted, journey_id):
    scripted.push(opening(Q1))
    assert (await client.post(f"/journeys/{journey_id}/discovery/start")).status_code == 200


async def test_start_during_an_in_flight_answer_returns_its_outcome_not_a_second_decision(async_client, scripted_async):
    journey_id = await new_journey(async_client)
    await _start(async_client, scripted_async, journey_id)
    gate = Gate(turn(question=Q2, state=GROUNDED["understanding"] and {"understanding": GROUNDED["understanding"]}))
    decoy = turn(ready=True, state=GROUNDED)               # the outcome a duplicate step would have produced
    scripted_async.push(gate, decoy)

    answer = asyncio.create_task(async_client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "I know the forward pass."}))
    await asyncio.wait_for(gate.entered.wait(), 5)
    reload = asyncio.create_task(async_client.post(f"/journeys/{journey_id}/discovery/start"))
    await wait_until(lambda: discovery_locks.holders(journey_id) == 2)
    calls_while_waiting = scripted_async.calls
    gate.release.set()
    a, r = await asyncio.gather(answer, reload)

    assert calls_while_waiting == 2                        # opening + the in-flight analysis only
    assert scripted_async.calls == 2 and len(scripted_async.queue) == 1  # the decoy was never consumed
    assert a.json()["question_index"] == 2 and r.json()["question_index"] == 2
    assert r.json()["is_finished"] is False
    assert rows(journey_id) == [(1, True), (2, False)]
    assert status(journey_id) == "discovery"               # NOT discovery_completed with an open question

    # The conversation is not stuck: the pending question can be answered
    scripted_async.push(turn(ready=True, state=GROUNDED))
    follow = await async_client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "The forward pass, concepts.", "question_index": 2})
    assert follow.status_code == 200 and follow.json()["is_finished"] is True


async def test_start_during_an_in_flight_finishing_answer_reports_completion_consistently(async_client, scripted_async):
    journey_id = await new_journey(async_client)
    await _start(async_client, scripted_async, journey_id)
    gate = Gate(turn(ready=True, state=GROUNDED))
    scripted_async.push(gate, turn(question="A decoy follow-up question that must never be created?"))

    answer = asyncio.create_task(async_client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "The forward pass, concepts."}))
    await asyncio.wait_for(gate.entered.wait(), 5)
    reload = asyncio.create_task(async_client.post(f"/journeys/{journey_id}/discovery/start"))
    await wait_until(lambda: discovery_locks.holders(journey_id) == 2)
    gate.release.set()
    a, r = await asyncio.gather(answer, reload)

    assert a.json()["is_finished"] is True and r.json()["is_finished"] is True
    assert rows(journey_id) == [(1, True)]                 # no orphan question after completion
    assert status(journey_id) == "discovery_completed"
    assert scripted_async.calls == 2


async def test_many_simultaneous_requests_still_advance_the_journey_exactly_once(async_client, scripted_async):
    journey_id = await new_journey(async_client)
    await _start(async_client, scripted_async, journey_id)
    gate = Gate(turn(question=Q2, state={"understanding": GROUNDED["understanding"]}))
    scripted_async.push(gate)
    scripted_async.default = turn(ready=True, state=GROUNDED)  # any extra model call would finish discovery

    answer = asyncio.create_task(async_client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "I know the forward pass."}))
    await asyncio.wait_for(gate.entered.wait(), 5)
    reloads = [asyncio.create_task(async_client.post(f"/journeys/{journey_id}/discovery/start")) for _ in range(5)]
    await wait_until(lambda: discovery_locks.holders(journey_id) == 6)
    gate.release.set()
    results = await asyncio.gather(answer, *reloads)

    assert {r.json()["question_index"] for r in results} == {2}
    assert all(r.json()["is_finished"] is False for r in results)
    assert scripted_async.calls == 2
    assert rows(journey_id) == [(1, True), (2, False)] and status(journey_id) == "discovery"


# ---------------------------------------------------------------------------
# Double submission and stale submissions
# ---------------------------------------------------------------------------

async def test_a_stale_second_submit_cannot_land_on_the_next_question(async_client, scripted_async):
    journey_id = await new_journey(async_client)
    await _start(async_client, scripted_async, journey_id)
    gate = Gate(turn(question=Q2, state={"understanding": GROUNDED["understanding"]}))
    scripted_async.push(gate)

    first = asyncio.create_task(async_client.post(
        f"/journeys/{journey_id}/discovery/answer", json={"answer": "I know the forward pass.", "question_index": 1}))
    await asyncio.wait_for(gate.entered.wait(), 5)
    stale = asyncio.create_task(async_client.post(
        f"/journeys/{journey_id}/discovery/answer", json={"answer": "I know the forward pass.", "question_index": 1}))
    await wait_until(lambda: discovery_locks.holders(journey_id) == 2)
    gate.release.set()
    r1, r2 = await asyncio.gather(first, stale)

    assert r1.status_code == 200 and r2.status_code == 409
    assert rows(journey_id) == [(1, True), (2, False)]     # the duplicate text did not answer question 2


async def test_cancelled_answer_request_keeps_the_answer_and_releases_the_lock(async_client, scripted_async):
    journey_id = await new_journey(async_client)
    await _start(async_client, scripted_async, journey_id)
    gate = Gate(turn(question=Q2, state={"understanding": GROUNDED["understanding"]}))
    scripted_async.push(gate)

    inflight = asyncio.create_task(async_client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "Saved before the model call."}))
    await asyncio.wait_for(gate.entered.wait(), 5)
    inflight.cancel()                                      # e.g. the browser tab closed mid-request
    with pytest.raises(asyncio.CancelledError):
        await inflight
    await wait_until(lambda: discovery_locks.holders(journey_id) == 0)

    assert rows(journey_id) == [(1, True)]                 # answer survived, no half-written successor
    scripted_async.push(turn(question=Q2, state={"understanding": GROUNDED["understanding"]}))
    resumed = await async_client.post(f"/journeys/{journey_id}/discovery/start")
    assert resumed.status_code == 200 and resumed.json()["question_index"] == 2
    assert rows(journey_id) == [(1, True), (2, False)]


async def test_a_timed_out_request_releases_the_lock_for_the_next_one(async_client, scripted_async, test_settings):
    from discovery_helpers import Sleep
    test_settings.discovery_request_timeout_seconds = 0.2
    journey_id = await new_journey(async_client)
    await _start(async_client, scripted_async, journey_id)
    scripted_async.push(Sleep(30))
    timed_out = await async_client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "Saved answer."})
    assert timed_out.status_code == 503
    assert discovery_locks.active() == 0
    scripted_async.push(turn(question=Q2, state={"understanding": GROUNDED["understanding"]}))
    assert (await async_client.post(f"/journeys/{journey_id}/discovery/start")).json()["question_index"] == 2


# ---------------------------------------------------------------------------
# Different journeys are independent
# ---------------------------------------------------------------------------

async def test_a_slow_journey_does_not_block_another(async_client, scripted_async):
    slow_id = await new_journey(async_client)
    fast_id = await new_journey(async_client)
    gate = Gate(opening(Q1))
    scripted_async.push(gate, opening("Another journey's own opening question, about something else?"))

    slow = asyncio.create_task(async_client.post(f"/journeys/{slow_id}/discovery/start"))
    await asyncio.wait_for(gate.entered.wait(), 5)
    fast = await asyncio.wait_for(async_client.post(f"/journeys/{fast_id}/discovery/start"), 5)
    assert fast.status_code == 200 and not slow.done()
    gate.release.set()
    assert (await slow).status_code == 200
