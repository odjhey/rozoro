import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from rozoro_monitor.herdr import MembershipMonitor, PaneLevel, inventory
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

    async def test_periodic_style_scan_repairs_missed_gone_and_reappear(self):
        (self.state/'a.meta').write_text('pane=p1\n'); self.levels['p1']=PaneLevel('p1','unknown',False)
        await self.monitor.start(); self.assertIn(('a',False,'unknown'),self.seen)
        self.levels['p1']=PaneLevel('p1','idle',True); await self.monitor.scan()
        self.assertIn(('a',True,'idle'),self.seen)

    async def test_unrelated_event_not_interrupted_by_metadata_rewrite(self):
        (self.state/'a.meta').write_text('pane=p1\n'); (self.state/'b.meta').write_text('pane=p2\n')
        await self.monitor.start(); sub=self.subs[-1]
        (self.state/'b.meta').write_text('pane=p2\nchanged=yes\n'); await self.monitor.scan()
        self.assertIs(sub,self.subs[-1])
        await sub.queue.put(PaneLevel('p1','done',True)); await asyncio.sleep(0)
        self.assertIn(('a',True,'done'),self.seen)

    async def test_stream_error_forces_rebuild_with_same_membership(self):
        (self.state/'a.meta').write_text('pane=p1\n'); await self.monitor.start()
        first = self.subs[-1]
        await first.queue.put(ConnectionError('lost'))
        for _ in range(20):
            if self.subs[-1] is not first: break
            await asyncio.sleep(.01)
        self.assertIsNot(first, self.subs[-1]); self.assertTrue(self.monitor.connected)

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
