"""Local bridge ownership regressions. Never imports live integration tests."""
import asyncio
import unittest
from bridge import Bridge
from test_bridge_local import FakeClient

class BridgeSafetyTests(unittest.TestCase):
    def test_foreign_cell_is_not_overwritten(self):
        async def case():
            b=Bridge(None); b.client=FakeClient()
            b.client.cells=[{'id':'reserved','source':'important_user_code()'}]
            with self.assertRaises(RuntimeError):
                await b.set_code('reserved','print(1)')
            self.assertEqual(b.client.cells[0]['source'],'important_user_code()')
        asyncio.run(case())

    def test_code_forwards_explicit_rpc_timeout(self):
        async def case():
            b=Bridge(None);b.client=FakeClient();seen=[]
            async def run(cell,timeout=240): seen.append(timeout);return 'ok'
            b.run=run
            self.assertEqual(await b.code('print(1)',timeout=90),'ok')
            self.assertEqual(seen,[90])
        asyncio.run(case())

    def test_duplicate_control_cells_are_rejected(self):
        async def case():
            b=Bridge(None); b.client=FakeClient()
            b.client.cells=[{'id':'a','source':'# WALTER_TRANSFER_CONTROL\nprint(1)'},
                            {'id':'b','source':'# WALTER_TRANSFER_CONTROL\nprint(2)'}]
            with self.assertRaises(RuntimeError): await b.code('print(3)')
        asyncio.run(case())

    def test_owned_cell_can_be_updated_without_duplicate(self):
        async def case():
            b=Bridge(None); b.client=FakeClient()
            a=await b.set_code('walter-job','print(1)')
            z=await b.set_code('walter-job','print(2)')
            self.assertEqual(a,z)
            self.assertEqual(b.client.adds,1)
            self.assertTrue(b.client.cells[0]['source'].endswith('print(2)'))
        asyncio.run(case())

class ResourcesTests(unittest.TestCase):
    def test_disconnected_toolbar_is_not_proof_of_zero_allocations(self):
        class BrowserStub:
            def assert_target(self): pass
        b=Bridge(BrowserStub())
        b.runtime_state=lambda: {'disconnected':True}
        b.resources=lambda: {'active_sessions':1}
        from unittest.mock import patch
        with patch('bridge.time.monotonic',side_effect=[0,21]):
            with self.assertRaises(RuntimeError): b.delete_test_runtime()

    def test_live_balance_and_zero_sessions_are_explicit(self):
        from bridge import parse_resources
        r=parse_resources(['Available: 82.84 compute units',
                           'Usage rate: approximately 0 per hour',
                           'You have 0 active sessions.'])
        self.assertEqual(r['compute_units'],82.84)
        self.assertEqual(r['active_sessions'],0)
        self.assertEqual(r['rate_text'],'Usage rate: approximately 0 per hour')

    def test_open_resources_panel_is_read_without_toggling_it_closed(self):
        class BrowserStub:
            def assert_target(self): pass
            def evaluate(self,expression):
                return ['Available: 82.84 compute units',
                        'Usage rate: approximately 0 per hour',
                        'You have 0 active sessions.']
        b=Bridge(BrowserStub())
        b.runtime_menu=lambda: self.fail('Already-open resources panel must not be toggled')
        self.assertEqual(b.resources()['active_sessions'],0)

    def test_partial_live_panel_waits_for_complete_fields_without_toggling(self):
        class BrowserStub:
            def __init__(self): self.calls=0
            def assert_target(self): pass
            def evaluate(self,expression):
                self.calls+=1
                if self.calls==1:return ['Available: 82.84 compute units']
                return ['Available: 82.84 compute units',
                        'Usage rate: approximately 0 per hour',
                        'You have 0 active sessions.']
        b=Bridge(BrowserStub())
        b.runtime_menu=lambda: self.fail('Partial open panel must not be toggled')
        self.assertEqual(b.resources()['active_sessions'],0)

    def test_missing_live_fields_fail_closed(self):
        from bridge import parse_resources
        with self.assertRaises(RuntimeError): parse_resources(['Available: 82.84 compute units'])

if __name__=='__main__': unittest.main()
