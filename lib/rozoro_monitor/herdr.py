"""Resident, gap-safe Herdr membership and defensive liveness."""
from __future__ import annotations

import asyncio
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Mapping, Protocol

MAX_META_BYTES = 64 * 1024
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$")

@dataclass(frozen=True)
class Member:
    task_id: str
    pane_id: str

@dataclass(frozen=True)
class PaneLevel:
    pane_id: str
    status: str
    exists: bool | None                 # None means observation failed/unknown
    revision: int | None = None

@dataclass(frozen=True)
class Inventory:
    members: Mapping[str, Member]
    errors: tuple[str, ...] = ()

class Subscription(Protocol):
    async def start(self) -> None: ...
    async def events(self): ...
    async def close(self) -> None: ...

SubscriberFactory = Callable[[tuple[str, ...]], Subscription]
LevelReader = Callable[[str], Awaitable[PaneLevel]]
Reconciler = Callable[[str, PaneLevel], Awaitable[None]]

def inventory(state_dir: str | os.PathLike[str]) -> Inventory:
    """Boundedly read private, no-follow regular metadata entries.

    Invalid/torn entries are errors, never evidence that a previously known
    task or pane disappeared.
    """
    members: dict[str, Member] = {}; errors: list[str] = []
    directory = Path(state_dir)
    try:
        dfd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        return Inventory({}, (f"state directory: {exc}",))
    try:
        dinfo = os.fstat(dfd)
        if dinfo.st_uid != os.geteuid() or stat.S_IMODE(dinfo.st_mode) & 0o077:
            return Inventory({}, ("state directory is not owner-private",))
        for name in sorted(os.listdir(dfd)):
            if not name.endswith(".meta"):
                continue
            task_id = name[:-5]
            if not _ID.fullmatch(task_id):
                errors.append(f"invalid task id: {name}"); continue
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0), dir_fd=dfd)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                        raise ValueError("not an owner-controlled regular file")
                    raw = os.read(fd, MAX_META_BYTES + 1)
                    if len(raw) > MAX_META_BYTES: raise ValueError("oversized")
                finally: os.close(fd)
                text = raw.decode("utf-8")
                fields: dict[str, str] = {}
                for line in text.splitlines():
                    if not line or "=" not in line: raise ValueError("malformed line")
                    key, value = line.split("=", 1)
                    if not key or key in fields: raise ValueError("malformed fields")
                    fields[key] = value
                pane = fields.get("pane", "")
                if not pane or len(pane) > 128 or any(c.isspace() for c in pane): raise ValueError("invalid pane")
                members[task_id] = Member(task_id, pane)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(f"{name}: {exc}")
    finally: os.close(dfd)
    return Inventory(members, tuple(errors))

class MembershipMonitor:
    def __init__(self, state_dir, subscriber: SubscriberFactory, level_reader: LevelReader,
                 reconcile: Reconciler, *, scan_interval=30.0, hint_interval=.20,
                 debounce=.15, drain_interval=.05):
        if min(scan_interval, hint_interval) <= 0 or min(debounce, drain_interval) < 0: raise ValueError("invalid timing")
        self.state_dir=Path(state_dir); self.subscriber=subscriber; self.level_reader=level_reader; self.reconcile=reconcile
        self.scan_interval=scan_interval; self.hint_interval=hint_interval; self.debounce=debounce; self.drain_interval=drain_interval
        self.members: dict[str,Member]={}; self._subscription=None; self._consumer=None; self._runner=None; self._hints=None
        self._wake=asyncio.Event(); self.connected=False; self.last_error=None; self.last_scan_errors=()
        self._force_rebuild=False; self._dir_signature=None
        self._active_token=None; self._pane_epoch: dict[str,int]={}; self._apply_lock=asyncio.Lock()
        self._route_generation: dict[str,int]={}
    def hint(self): self._wake.set()
    async def start(self):
        try: await self.scan(force=True)
        except Exception as exc: self.last_error=str(exc)[:128]
        self._runner=asyncio.create_task(self._run()); self._hints=asyncio.create_task(self._watch_hints())
    def _signature(self):
        try:
            st=self.state_dir.stat(); return (st.st_mtime_ns, st.st_ctime_ns)
        except OSError: return None
    async def _watch_hints(self):
        """Directory metadata changes are debounced hints; full scans decide truth."""
        try:
            self._dir_signature=self._signature()
            while True:
                await asyncio.sleep(self.hint_interval)
                value=self._signature()
                if value != self._dir_signature: self._dir_signature=value; self.hint()
        except asyncio.CancelledError: pass
    async def _run(self):
        try:
            while True:
                try:
                    await asyncio.wait_for(self._wake.wait(),self.scan_interval); self._wake.clear(); await asyncio.sleep(self.debounce)
                except TimeoutError: pass
                try: await self.scan(force=self._force_rebuild)
                except Exception as exc: self.connected=False; self.last_error=str(exc)[:128]
        except asyncio.CancelledError: pass
    async def scan(self, *, force=False):
        result=inventory(self.state_dir); self.last_scan_errors=result.errors
        if result.errors: self.last_error=result.errors[-1][:128]
        # Keep known entries omitted by malformed/torn reads. They are unknown,
        # not gone; valid removals remain removals.
        found=dict(result.members)
        for task, member in self.members.items():
            if task not in found and any(error.startswith(task+".meta:") for error in result.errors): found[task]=member
        changed=set(found) != set(self.members) or any(found[k].pane_id != self.members[k].pane_id for k in set(found)&set(self.members))
        if force or self._force_rebuild or changed:
            await self._replace(found); self._force_rebuild=False; return True
        levels_ok=await self._levels(self.members)
        self.connected=bool(self.members) and levels_ok and self._consumer is not None and not self._consumer.done()
        if self.connected and not self.last_scan_errors: self.last_error=None
        elif not self.members: self.last_error="no resident members; configured Herdr socket untested"
        return False
    async def _replace(self, found):
        panes=tuple(sorted({m.pane_id for m in found.values()})); new=self.subscriber(panes); consumer=None; previous=self.members
        previous_token=self._active_token; previous_routes=dict(self._route_generation); token=object()
        changed_tasks={task for task in set(previous)|set(found)
                       if previous.get(task) != found.get(task)}
        for task in changed_tasks:
            self._route_generation[task]=self._route_generation.get(task,0)+1
        routing={task:(member,self._route_generation.get(task,0)) for task,member in found.items()}
        try:
            await new.start(); self.members=dict(found); self._active_token=token
            consumer=asyncio.create_task(self._consume(new,token,routing))
            levels_ok=await self._levels(found)
            if consumer.done():
                await consumer
                raise ConnectionError("new Herdr stream died during level reconciliation")
        except Exception:
            self.members=previous; self._active_token=previous_token; self._route_generation=previous_routes
            if consumer: consumer.cancel(); await asyncio.gather(consumer,return_exceptions=True)
            await new.close(); raise
        old,old_consumer=self._subscription,self._consumer
        self._subscription,self._consumer=new,consumer
        self.connected=bool(found) and levels_ok and not consumer.done()
        if self.connected and not self.last_scan_errors: self.last_error=None
        elif not found: self.last_error="no resident members; configured Herdr socket untested"
        # Both streams stay routed during the bounded drain. Old queued edges
        # are consumed before its transport is closed and task is cancelled.
        if old:
            await asyncio.sleep(self.drain_interval); await old.close()
        if old_consumer:
            try: await asyncio.wait_for(old_consumer,self.drain_interval)
            except TimeoutError: old_consumer.cancel(); await asyncio.gather(old_consumer,return_exceptions=True)
            except Exception: pass  # the replacement was commonly caused by this stream failure
    async def _apply(self,task_id,level,*,expected_epoch=None,expected_route=None):
        async with self._apply_lock:
            if expected_epoch is not None and self._pane_epoch.get(level.pane_id,0) != expected_epoch:
                return
            if expected_route is not None and self._route_generation.get(task_id,0) != expected_route:
                return
            await self.reconcile(task_id,level)
    async def _levels(self,members):
        ok=True; current_rpc_error=None
        for member in members.values():
            frontier=self._pane_epoch.get(member.pane_id,0)
            try: level=await self.level_reader(member.pane_id)
            except Exception as exc:
                current_rpc_error=str(exc)[:128]; self.connected=False
                level=PaneLevel(member.pane_id,"unknown",None)
            if level.exists is None:
                ok=False; self.connected=False
            await self._apply(member.task_id,level,expected_epoch=frontier,
                              expected_route=self._route_generation.get(member.task_id,0))
        if not ok:
            # Replace stale scan/zero-membership text with this scan's RPC
            # truth. Preserve only a specific exception observed right now.
            self.last_error=current_rpc_error or "Herdr level RPC unavailable"
        return ok
    async def _consume(self,sub,token,routing):
        try:
            async for level in sub.events():
                self._pane_epoch[level.pane_id]=self._pane_epoch.get(level.pane_id,0)+1
                for member,route in tuple(routing.values()):
                    if member.pane_id==level.pane_id:
                        await self._apply(member.task_id,level,expected_route=route)
            raise ConnectionError("Herdr subscription ended")
        except asyncio.CancelledError: pass
        except Exception as exc:
            if token is self._active_token:
                self.connected=False; self.last_error=str(exc)[:128]; self._force_rebuild=True; self.hint()
    def health(self):
        return {"herdr_connected":self.connected,"herdr_last_error":self.last_error,
                "herdr_inventory_errors":len(self.last_scan_errors),"herdr_task_count":len(self.members)}
    async def close(self):
        for task in (self._runner,self._hints):
            if task: task.cancel()
        await asyncio.gather(*(t for t in (self._runner,self._hints) if t),return_exceptions=True)
        if self._subscription: await self._subscription.close()
        if self._consumer: self._consumer.cancel(); await asyncio.gather(self._consumer,return_exceptions=True)
        self.connected=False

class EmptySubscription:
    async def start(self): pass
    async def events(self):
        await asyncio.Future()
        if False: yield None
    async def close(self): pass

class UnixHerdrSubscription:
    def __init__(self,socket_path,panes,*,timeout=5.0,shard_on_missing=True):
        self.socket_path=socket_path; self.panes=panes; self.timeout=timeout; self.reader=None; self.writer=None
        self.shard_on_missing=shard_on_missing; self._children=[]; self._pumps=[]; self._queue=None
    async def _start_direct(self):
        self.reader,self.writer=await asyncio.wait_for(asyncio.open_unix_connection(self.socket_path),self.timeout)
        request={"id":"rozorod-membership","method":"events.subscribe","params":{"subscriptions":[{"type":"pane.agent_status_changed","pane_id":p} for p in self.panes]}}
        self.writer.write((json.dumps(request,separators=(",",":"))+"\n").encode()); await asyncio.wait_for(self.writer.drain(),self.timeout)
        reply=json.loads((await asyncio.wait_for(self.reader.readline(),self.timeout)).decode())
        if reply.get("error") is not None: raise HerdrAPIError(reply["error"])
        if (reply.get("result") or {}).get("type")!="subscription_started": raise RuntimeError("Herdr rejected subscription")
    async def start(self):
        try:
            await self._start_direct(); return
        except HerdrAPIError as exc:
            await self.close()
            if not self.shard_on_missing or len(self.panes) < 2 or not _not_found(exc.error): raise
        # Herdr rejects a whole multi-pane subscription when any pane is gone.
        # Retry independently so stale metadata cannot suppress live panes.
        self._queue=asyncio.Queue()
        try:
            for pane in self.panes:
                child=UnixHerdrSubscription(self.socket_path,(pane,),timeout=self.timeout,shard_on_missing=False)
                try: await child.start()
                except HerdrAPIError as exc:
                    await child.close()
                    if _not_found(exc.error): continue
                    raise
                self._children.append(child)
            self._pumps=[asyncio.create_task(self._pump(child)) for child in self._children]
        except Exception:
            await self.close(); raise
    async def _pump(self,child):
        try:
            async for level in child.events(): await self._queue.put(level)
        except asyncio.CancelledError: pass
        except Exception as exc: await self._queue.put(exc)
    async def events(self):
        if self._queue is not None:
            while True:
                item=await self._queue.get()
                if isinstance(item,Exception): raise item
                yield item
        while self.reader:
            line=await self.reader.readline()
            if not line: raise ConnectionError("Herdr subscription closed")
            msg=json.loads(line)
            if msg.get("event")!="pane.agent_status_changed": continue
            data=msg.get("data") or {}; pane=data.get("pane_id")
            if pane:
                rev=data.get("state_change_seq",data.get("revision")); yield PaneLevel(pane,data.get("agent_status") or "unknown",True,rev if isinstance(rev,int) else None)
    async def close(self):
        for pump in self._pumps: pump.cancel()
        await asyncio.gather(*self._pumps,return_exceptions=True); self._pumps=[]
        for child in self._children: await child.close()
        self._children=[]
        if self.writer:
            self.writer.close(); await self.writer.wait_closed(); self.writer=None

class HerdrAPIError(RuntimeError):
    def __init__(self,error):
        self.error=error; super().__init__(str(error))

def _not_found(error):
    text=json.dumps(error,sort_keys=True).casefold()
    return "not_found" in text or "not found" in text or "pane_not_found" in text

async def herdr_rpc(socket_path,method,params,*,timeout=3.0):
    """One bounded RPC to the configured socket; never consults default CLI state."""
    reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(socket_path),timeout)
    try:
        writer.write((json.dumps({"id":"rozorod-level","method":method,"params":params},separators=(",",":"))+"\n").encode())
        await asyncio.wait_for(writer.drain(),timeout)
        line=await asyncio.wait_for(reader.readline(),timeout)
        if not line: raise ConnectionError("Herdr RPC closed")
        response=json.loads(line)
        if response.get("error") is not None: raise HerdrAPIError(response["error"])
        return response
    finally:
        writer.close(); await writer.wait_closed()

async def read_pane_level(socket_path,pane_id,*,timeout=3.0):
    """Use Herdr 0.8.2 schemas and distinguish absence from uncertainty."""
    try:
        data=await herdr_rpc(socket_path,"agent.get",{"target":pane_id},timeout=timeout/2)
        result=data.get("result") or {}; agent=result.get("agent") or result
        return PaneLevel(pane_id,agent.get("agent_status") or "unknown",True,agent.get("state_change_seq"))
    except HerdrAPIError as exc:
        if not _not_found(exc.error): return PaneLevel(pane_id,"unknown",None)
    except (OSError,TimeoutError,ConnectionError,ValueError):
        return PaneLevel(pane_id,"unknown",None)
    try:
        await herdr_rpc(socket_path,"pane.get",{"pane_id":pane_id},timeout=timeout/2)
        return PaneLevel(pane_id,"unknown",True)
    except HerdrAPIError as exc:
        return PaneLevel(pane_id,"unknown",False if _not_found(exc.error) else None)
    except (OSError,TimeoutError,ConnectionError,ValueError):
        return PaneLevel(pane_id,"unknown",None)
