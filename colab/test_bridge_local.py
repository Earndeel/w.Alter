"""Local-only fake MCP for cell idempotence; no Google or browser calls."""
import asyncio
import unittest
from types import SimpleNamespace
from bridge import Bridge

class FakeClient:
    def __init__(self):
        self.cells=[]
        self.adds=0
    async def call_tool(self,name,args):
        if name=='get_cells':return SimpleNamespace(structured_content={'cells':[dict(c) for c in self.cells]})
        if name=='add_code_cell':
            self.adds+=1
            self.cells.append({'id':'actual-'+str(self.adds),'source':args['code']})
        elif name=='update_cell':
            next(c for c in self.cells if c['id']==args['cellId'])['source']=args['content']
        else:raise AssertionError(name)
        return SimpleNamespace(structured_content={})

class BridgeTests(unittest.TestCase):
    def test_runtime_menu_click_uses_browser_native_pointer(self):
        class BrowserStub:
            def __init__(self):self.actions=[]
            def evaluate(self,expression):return {'x':125,'y':250}
            def action(self,route,**args):self.actions.append((route,args));return {'ok':True}
        browser=BrowserStub()
        Bridge(browser).click_menu('Disconnect and delete runtime')
        self.assertEqual(browser.actions,[('/tab/click-at',{'x':125,'y':250})])

    def test_click_to_connect_text_proves_disconnected(self):
        import json,subprocess
        class DOMStub:
            def evaluate(self,expression):
                harness='const document={querySelectorAll:()=>[{getBoundingClientRect:()=>({width:10}),getAttribute:()=>null,tagName:"MD-TEXT-BUTTON",textContent:"Click to connect"}]};'
                return json.loads(subprocess.check_output(['node','-e',harness+'console.log(JSON.stringify('+expression+'))'],text=True))
        self.assertTrue(Bridge(DOMStub()).runtime_state()['disconnected'])

    def test_repeated_same_bootstrap_does_not_add_duplicate_cells(self):
        async def case():
            bridge=Bridge(None);bridge.client=FakeClient()
            a=await bridge.set_code('walter-cache-bootstrap','print(1)')
            b=await bridge.set_code('walter-cache-bootstrap','print(1)')
            self.assertEqual(a,b)
            self.assertEqual(bridge.client.adds,1)
        asyncio.run(case())

if __name__=='__main__':unittest.main()
