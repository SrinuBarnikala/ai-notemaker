"""
Per-journey serialization of discovery requests.

Discovery handlers read the conversation, call a slow model, then write the outcome. Without
serialization a reload (or a second tab) during that window can run the same step twice and persist
two different outcomes. Holding this lock across the whole read-decide-write sequence, and re-reading
state after acquiring it, makes those requests take turns.

LIMITATION: this is an in-process lock. It protects a single server process (how the app is run
today). Several worker processes would not share it; the unique index on
(journey_id, question_index) is the cross-process backstop against duplicate questions, but a
"continue" vs "finish" race between processes would not be prevented.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, List


class JourneyLocks:
    def __init__(self) -> None:
        # journey_id -> [lock, number of requests holding or waiting for it]
        self._entries: Dict[str, List] = {}

    @asynccontextmanager
    async def hold(self, journey_id: str) -> AsyncIterator[None]:
        entry = self._entries.get(journey_id)
        if entry is None:
            entry = self._entries[journey_id] = [asyncio.Lock(), 0]
        entry[1] += 1  # registered before waiting, so the entry cannot be dropped under a waiter
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if entry[1] == 0:
                # Nobody holds or waits: drop it so the dict never grows and no lock outlives its event loop.
                self._entries.pop(journey_id, None)

    def active(self) -> int:
        """Number of journeys with a lock entry (holder or waiter); 0 when idle, so nothing leaks."""
        return len(self._entries)

    def holders(self, journey_id: str) -> int:
        """Requests currently holding or waiting for this journey's lock."""
        entry = self._entries.get(journey_id)
        return entry[1] if entry else 0


discovery_locks = JourneyLocks()
