"""Resident Herdr membership and defensive liveness reconciliation.

Filesystem notifications are only hints.  The inventory is the set of valid
``state/*.meta`` names, and every changed set is installed by subscribing first
and then reading pane levels, closing the edge/level race.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Mapping, Protocol


@dataclass(frozen=True)
class Member:
    task_id: str
    pane_id: str | None


@dataclass(frozen=True)
class PaneLevel:
    pane_id: str
    status: str
    exists: bool
    revision: int | None = None


class Subscription(Protocol):
    async def start(self) -> None: ...       # returns after subscription_started
    async def events(self): ...
    async def close(self) -> None: ...


SubscriberFactory = Callable[[tuple[str, ...]], Subscription]
LevelReader = Callable[[str], Awaitable[PaneLevel]]
Reconciler = Callable[[str, PaneLevel], Awaitable[None]]


def inventory(state_dir: str | os.PathLike[str]) -> dict[str, Member]:
    """Read actual task IDs. Contents matter only for the task's pane mapping."""
    result: dict[str, Member] = {}
    for path in sorted(Path(state_dir).glob("*.meta")):
        if not path.is_file() or not path.stem or "/" in path.stem:
            continue
        pane = None
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("pane="):
                    pane = line[5:] or None
                    break
        except OSError:
            continue
        result[path.stem] = Member(path.stem, pane)
    return result


class MembershipMonitor:
    """Own one Herdr stream and repair membership periodically.

    ``hint()`` is cheap and debounced. Same-ID rewrites never rebuild the
    subscription; changed pane contents are picked up by the periodic level
    scan without disturbing unrelated crews.
    """
    def __init__(self, state_dir: str | os.PathLike[str], subscriber: SubscriberFactory,
                 level_reader: LevelReader, reconcile: Reconciler, *,
                 scan_interval: float = 30.0, debounce: float = .15):
        if scan_interval <= 0 or debounce < 0:
            raise ValueError("invalid membership timing")
        self.state_dir = Path(state_dir)
        self.subscriber = subscriber
        self.level_reader = level_reader
        self.reconcile = reconcile
        self.scan_interval = scan_interval
        self.debounce = debounce
        self.members: dict[str, Member] = {}
        self._subscription: Subscription | None = None
        self._consumer: asyncio.Task | None = None
        self._runner: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._closed = False
        self.connected = False
        self.last_error: str | None = None

    def hint(self) -> None:
        self._wake.set()

    async def start(self) -> None:
        await self.scan(force=True)
        self._runner = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while True:
                try:
                    await asyncio.wait_for(self._wake.wait(), self.scan_interval)
                    self._wake.clear()
                    await asyncio.sleep(self.debounce)
                except TimeoutError:
                    pass
                await self.scan()
        except asyncio.CancelledError:
            pass

    async def scan(self, *, force: bool = False) -> bool:
        found = inventory(self.state_dir)
        # Membership is task identity, deliberately not metadata bytes/pane value.
        if not force and found.keys() == self.members.keys():
            # Membership identity is the filename. Ignore same-ID content
            # rewrites entirely, including a transient/torn pane field, and
            # keep the established subscription and routing map untouched.
            await self._levels(self.members)
            return False
        await self._replace(found)
        return True

    async def _replace(self, found: Mapping[str, Member]) -> None:
        panes = tuple(sorted({m.pane_id for m in found.values() if m.pane_id}))
        new = self.subscriber(panes)
        new_consumer = None
        previous_members = self.members
        try:
            await new.start()                 # synchronization point
            self.members = dict(found)        # event routing is live before levels
            new_consumer = asyncio.create_task(self._consume(new))
            await self._levels(found)         # closes subscribe/snapshot gap
        except Exception as exc:
            self.members = previous_members
            if new_consumer:
                new_consumer.cancel()
            await new.close()
            self.connected = False
            self.last_error = str(exc)[:128]
            raise
        old, old_consumer = self._subscription, self._consumer
        self._subscription, self._consumer = new, new_consumer
        self.connected = True
        self.last_error = None
        if old_consumer:
            old_consumer.cancel()
            await asyncio.gather(old_consumer, return_exceptions=True)
        if old:
            await old.close()

    async def _levels(self, members: Mapping[str, Member]) -> None:
        for member in members.values():
            if member.pane_id is None:
                await self.reconcile(member.task_id, PaneLevel("", "unknown", False))
                continue
            try:
                level = await self.level_reader(member.pane_id)
            except Exception as exc:
                level = PaneLevel(member.pane_id, "unknown", False)
                self.last_error = str(exc)[:128]
            await self.reconcile(member.task_id, level)

    async def _consume(self, subscription: Subscription) -> None:
        try:
            async for level in subscription.events():
                for member in tuple(self.members.values()):
                    if member.pane_id == level.pane_id:
                        await self.reconcile(member.task_id, level)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)[:128]
            self.hint()

    async def close(self) -> None:
        self._closed = True
        for task in (self._runner, self._consumer):
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in (self._runner, self._consumer) if t), return_exceptions=True)
        if self._subscription:
            await self._subscription.close()
        self.connected = False


class EmptySubscription:
    """A connected no-op stream used when resident membership is empty."""
    async def start(self) -> None: pass
    async def events(self):
        if False:
            yield None
        await asyncio.Future()
    async def close(self) -> None: pass


class UnixHerdrSubscription:
    """Small stdlib implementation of Herdr's public events.subscribe API."""
    def __init__(self, socket_path: str, panes: tuple[str, ...]):
        self.socket_path, self.panes = socket_path, panes
        self.reader = self.writer = None

    async def start(self) -> None:
        self.reader, self.writer = await asyncio.open_unix_connection(self.socket_path)
        request = {"id": "rozorod-membership", "method": "events.subscribe", "params": {
            "subscriptions": [{"type": "pane.agent_status_changed", "pane_id": p} for p in self.panes]}}
        self.writer.write((json.dumps(request, separators=(",", ":")) + "\n").encode())
        await self.writer.drain()
        reply = json.loads((await asyncio.wait_for(self.reader.readline(), 5)).decode())
        if (reply.get("result") or {}).get("type") != "subscription_started":
            raise RuntimeError("Herdr rejected subscription")

    async def events(self):
        while self.reader:
            line = await self.reader.readline()
            if not line:
                raise ConnectionError("Herdr subscription closed")
            message = json.loads(line)
            if message.get("event") != "pane.agent_status_changed":
                continue
            data = message.get("data") or {}
            pane = data.get("pane_id")
            if pane:
                revision = data.get("state_change_seq", data.get("revision"))
                yield PaneLevel(pane, data.get("agent_status") or "unknown", True,
                                revision if isinstance(revision, int) else None)

    async def close(self) -> None:
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
