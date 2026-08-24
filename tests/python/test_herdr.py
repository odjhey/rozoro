import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from rozoro_monitor.herdr import MembershipMonitor, PaneLevel, UnixHerdrSubscription, inventory, read_pane_level
from rozoro_monitor.store import EventStore


class FakeSubscription:
    def __init__(self, panes, log, during=None):
        self.panes, self.log, self.queue, self.during = panes, log, asyncio.Queue(), during
    async def start(self): self.log.append(("subscribe", self.panes))
    async def events(self):
        while True:
            item = await self.queue.get()
            if isinstance(item, Exception): raise item
            yield item
    async def close(self): self.log.append(("close", self.panes))


class MembershipTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_umask = os.umask(0o077)
        self.tmp = tempfile.TemporaryDirectory(); self.state = Path(self.tmp.name)
        self.log=[]; self.subs=[]; self.seen=[]; self.levels={}
        def factory(panes):
            sub=FakeSubscription(panes,self.log); self.subs.append(sub); return sub
        async def level(pane):
            self.log.append(("level",pane)); return self.levels.get(pane, PaneLevel(pane,"idle",True))
        async def reconcile(task, value): self.seen.append((task,value.exists,value.status))
        self.monitor=MembershipMonitor(self.state,factory,level,reconcile,scan_interval=99,debounce=0)
    async def asyncTearDown(self):
        await self.monitor.close(); self.tmp.cleanup(); os.umask(self.old_umask)

    async def test_inventory_uses_names_and_rewrite_does_not_reconnect(self):
        (self.state/'a.meta').write_text('pane=p1\nother=x\n')
        await self.monitor.start(); count=len(self.subs)
        (self.state/'a.meta').write_text('pane=p1\nother=y\n')
        self.assertFalse(await self.monitor.scan())
        self.assertEqual(count,len(self.subs))

    async def test_subscribe_precedes_levels_and_add_remove_preserve_edges(self):
        (self.state/'a.meta').write_text('pane=p1\n'); await self.monitor.start()
        self.assertLess(self.log.index(("subscribe",("p1",))), self.log.index(("level","p1")))
        (self.state/'b.meta').write_text('pane=p2\n'); await self.monitor.scan()
        await self.subs[-1].queue.put(PaneLevel('p2','done',True)); await asyncio.sleep(0)
        self.assertIn(('b',True,'done'),self.seen)
        (self.state/'a.meta').unlink(); await self.monitor.scan()
        self.assertEqual(self.subs[-1].panes,('p2',))

    async def test_health_requires_members_and_rpc_truth_then_recovers(self):
        await self.monitor.start()
        self.assertFalse(self.monitor.connected); self.assertIn('untested',self.monitor.last_error)
        (self.state/'a.meta').write_text('pane=p1\n'); self.levels['p1']=PaneLevel('p1','unknown',None)
        await self.monitor.scan(); self.assertFalse(self.monitor.connected)
        self.assertEqual(self.monitor.last_error,'Herdr level RPC unavailable')
        self.levels['p1']=PaneLevel('p1','idle',True)
        await self.monitor.scan(); self.assertTrue(self.monitor.connected); self.assertIsNone(self.monitor.last_error)

    async def test_periodic_style_scan_repairs_missed_gone_and_reappear(self):
        (self.state/'a.meta').write_text('pane=p1\n'); self.levels['p1']=PaneLevel('p1','unknown',False)
        await self.monitor.start(); self.assertIn(('a',False,'unknown'),self.seen)
        self.levels['p1']=PaneLevel('p1','idle',True); await self.monitor.scan()
        self.assertIn(('a',True,'idle'),self.seen)

    async def test_new_membership_activates_before_gone_and_rolls_back_staging_failure(self):
        events=[]
        async def activate(task): events.append(('activate',task))
        async def retire(task): events.append(('retire',task))
        async def reconcile(task,level): events.append(('reconcile',task,level.exists))
        async def level(pane):
            if pane == 'bad': raise ConnectionError('level failed')
            return PaneLevel(pane,'unknown',False)
        monitor=MembershipMonitor(self.state,lambda panes: FakeSubscription(panes,[]),level,reconcile,
                                  activate=activate,retire=retire,scan_interval=99,debounce=0)
        (self.state/'a.meta').write_text('pane=p1\n')
        await monitor.scan(force=True)
        self.assertLess(events.index(('activate','a')),events.index(('reconcile','a',False)))
        (self.state/'b.meta').write_text('pane=bad\n')
        with self.assertRaises(ConnectionError): await monitor.scan()
        self.assertEqual(events[-2:],[('activate','b'),('retire','b')])
        await monitor.close()

    async def test_unrelated_event_not_interrupted_by_metadata_rewrite(self):
        (self.state/'a.meta').write_text('pane=p1\n'); (self.state/'b.meta').write_text('pane=p2\n')
        await self.monitor.start(); sub=next(item for item in self.subs if item.panes == ('p1',)); count=len(self.subs)
        (self.state/'b.meta').write_text('pane=p2\nchanged=yes\n'); await self.monitor.scan()
        self.assertEqual(count,len(self.subs)); self.assertNotIn(("close",('p1',)),self.log)
        await sub.queue.put(PaneLevel('p1','done',True)); await asyncio.sleep(0)
        self.assertIn(('a',True,'done'),self.seen)

    async def test_event_after_subscribe_wins_over_stale_inflight_level(self):
        (self.state/'a.meta').write_text('pane=p1\n'); entered=asyncio.Event(); release=asyncio.Event(); seen=[]; subs=[]
        def factory(panes): sub=FakeSubscription(panes,[]); subs.append(sub); return sub
        async def level(_): entered.set(); await release.wait(); return PaneLevel('p1','unknown',False)
        async def reconcile(task,value): seen.append((task,value.exists,value.status))
        monitor=MembershipMonitor(self.state,factory,level,reconcile,scan_interval=99,debounce=0)
        start=asyncio.create_task(monitor.start()); await entered.wait()
        await subs[0].queue.put(PaneLevel('p1','done',True)); await asyncio.sleep(0); release.set(); await start
        try:
            self.assertIn(('a',True,'done'),seen); self.assertNotIn(('a',False,'unknown'),seen)
        finally: await monitor.close()

    async def test_stream_error_forces_rebuild_with_same_membership(self):
        (self.state/'a.meta').write_text('pane=p1\n'); await self.monitor.start()
        first = self.subs[-1]
        await first.queue.put(ConnectionError('lost'))
        for _ in range(20):
            if self.subs[-1] is not first: break
            await asyncio.sleep(.01)
        self.assertIsNot(first, self.subs[-1]); self.assertTrue(self.monitor.connected)

    async def test_old_replaced_route_cannot_resurrect_but_unrelated_old_route_drains(self):
        (self.state/'a.meta').write_text('pane=p1\n'); (self.state/'b.meta').write_text('pane=pb\n')
        self.levels['p1']=PaneLevel('p1','idle',True); self.levels['pb']=PaneLevel('pb','idle',True)
        await self.monitor.start(); old=next(item for item in self.subs if item.panes == ('p1',)); unrelated=next(item for item in self.subs if item.panes == ('pb',))
        (self.state/'a.meta').write_text('pane=p2\n'); self.levels['p2']=PaneLevel('p2','unknown',False)
        replacing=asyncio.create_task(self.monitor.scan())
        for _ in range(20):
            if any(item.panes == ('p2',) for item in self.subs): break
            await asyncio.sleep(.005)
        await old.queue.put(PaneLevel('p1','done',True))
        await unrelated.queue.put(PaneLevel('pb','done',True))
        await replacing
        self.assertNotIn(("close",('pb',)),self.log)
        self.assertNotIn(('a',True,'done'),self.seen)
        self.assertIn(('a',False,'unknown'),self.seen)
        self.assertIn(('b',True,'done'),self.seen)

    async def test_same_task_pane_replacement_rebuilds_but_field_rewrite_does_not(self):
        (self.state/'a.meta').write_text('pane=p1\n'); await self.monitor.start(); first=self.subs[-1]
        (self.state/'a.meta').write_text('pane=p2\n'); self.assertTrue(await self.monitor.scan())
        self.assertEqual(self.subs[-1].panes,('p2',)); self.assertIsNot(first,self.subs[-1])

    def test_inventory_rejects_symlink_oversize_and_invalid_id(self):
        target=self.state/'target'; target.write_text('pane=p\n')
        (self.state/'link.meta').symlink_to(target)
        (self.state/'huge.meta').write_bytes(b'pane=' + b'x'*70000)
        (self.state/'bad id.meta').write_text('pane=p\n')
        result=inventory(self.state)
        self.assertFalse(result.members); self.assertEqual(len(result.errors),3)

    def test_inventory_same_id(self):
        (self.state/'x.meta').write_text('pane=p\n')
        self.assertEqual(set(inventory(self.state).members),{'x'})

    async def test_subscription_keeps_live_pane_when_batch_contains_gone_pane(self):
        sock=str(self.state/'herdr.sock'); requests=[]; live_writer=None
        async def handler(reader,writer):
            nonlocal live_writer
            request=__import__('json').loads(await reader.readline()); requests.append(request)
            panes=[item['pane_id'] for item in request['params']['subscriptions']]
            if 'gone' in panes:
                reply={"id":"x","error":{"code":"pane_not_found","message":"gone"}}
            else:
                reply={"id":"x","result":{"type":"subscription_started"}}; live_writer=writer
            writer.write((__import__('json').dumps(reply)+'\n').encode()); await writer.drain()
            if 'gone' in panes: writer.close()
        server=await asyncio.start_unix_server(handler,sock)
        sub=UnixHerdrSubscription(sock,('gone','live'),timeout=.5)
        try:
            await sub.start()
            event={"event":"pane.agent_status_changed","data":{"pane_id":"live","agent_status":"done","state_change_seq":7}}
            live_writer.write((__import__('json').dumps(event)+'\n').encode()); await live_writer.drain()
            level=await asyncio.wait_for(anext(sub.events()),.5)
            self.assertEqual(level,PaneLevel('live','done',True,7))
            self.assertEqual([[s['pane_id'] for s in r['params']['subscriptions']] for r in requests],
                             [['gone','live'],['gone'],['live']])
        finally:
            await sub.close()
            if live_writer: live_writer.close()
            server.close(); await server.wait_closed()

    async def test_real_socket_uses_082_target_and_error_absence_vs_transport_unknown(self):
        sock=str(self.state/'herdr.sock'); requests=[]
        async def handler(reader,writer):
            request=__import__('json').loads(await reader.readline()); requests.append(request)
            if request['method']=='agent.get':
                reply={"id":"x","error":{"code":"agent_not_found","message":"not found"}}
            else:
                reply={"id":"x","error":{"code":"pane_not_found","message":"not found"}}
            writer.write((__import__('json').dumps(reply)+'\n').encode()); await writer.drain(); writer.close()
        server=await asyncio.start_unix_server(handler,sock)
        try: level=await read_pane_level(sock,'p1',timeout=.5)
        finally: server.close(); await server.wait_closed()
        self.assertFalse(level.exists)
        self.assertEqual(requests[0]['params'],{"target":"p1"})
        self.assertEqual(requests[1]['params'],{"pane_id":"p1"})
        unknown=await read_pane_level(str(self.state/'missing.sock'),'p1',timeout=.05)
        self.assertIsNone(unknown.exists)

    def test_certified_disconnect_from_quiescent_bumps_once_with_valid_frozen_tuple(self):
        db=self.state/'disconnect.db'; task=self.state/'tasks'/'task-d'; task.mkdir(parents=True)
        (task/'handoff.md').write_text('## turn 1 — done\nverdict: done\nreason: none\ndid: work\npending: none\ninputs-needed: none\nartifacts: none\n')
        base={"v":1,"session_id":"session-d","harness":"claude","role":"crew","task_id":"task-d"}
        with EventStore(db) as store:
            store.accept_event({**base,"type":"session.register","event_id":"rd","producer_seq":1})
            store.accept_event({**base,"type":"turn.stop","event_id":"sd","producer_seq":2,"background_active":False})
            before=store.health_snapshot()['generation']
            store.reconcile_herdr_liveness('task-d',pane_exists=True,adapter_connected=False)
            after=store.health_snapshot()['generation']; self.assertEqual(after,before+1)
            row=store.task_projection('task-d')
            self.assertEqual((row['report_state'],row['verdict'],row['actionable_reason']),('valid','done','none'))
            pending=store._connection.execute('SELECT actionable_reason FROM pending_generation_tasks WHERE generation=?',(after,)).fetchone()[0]
            self.assertEqual(pending,'unknown')
            store.reconcile_herdr_liveness('task-d',pane_exists=True,adapter_connected=False)
            self.assertEqual(store.health_snapshot()['generation'],after)

    def test_store_gone_reappear_is_unknown_and_never_clears_native_active(self):
        db = self.state / 'monitor.db'; task = self.state / 'tasks' / 'task-1'; task.mkdir(parents=True)
        base = {"v":1,"session_id":"session-1","harness":"claude","role":"crew","task_id":"task-1"}
        with EventStore(db) as store:
            store.accept_event({**base,"type":"session.register","event_id":"register","producer_seq":1})
            store.accept_event({**base,"type":"turn.stop","event_id":"stop","producer_seq":2,"background_active":True})
            generation = store.health_snapshot()['generation']
            store.reconcile_herdr_liveness('task-1', pane_exists=True)
            self.assertEqual(store.task_projection('task-1')['availability'],'waiting-background')
            self.assertEqual(store.health_snapshot()['generation'],generation)
            store.reconcile_herdr_liveness('task-1', pane_exists=False)
            self.assertEqual(store.task_projection('task-1')['availability'],'gone')
            store.reconcile_herdr_liveness('task-1', pane_exists=True)
            projection = store.task_projection('task-1')
            detail = __import__('json').loads(projection['projection_json'])
            self.assertEqual(projection['availability'],'waiting-background')
            self.assertEqual(detail['background'],'active')
            self.assertEqual(store.health_snapshot()['generation'],generation + 2)

if __name__ == '__main__': unittest.main()
