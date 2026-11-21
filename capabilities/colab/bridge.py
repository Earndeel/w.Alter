"""Bounded interactive controller for the official googlecolab/colab-mcp."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import re
import time
import uuid
import webbrowser
from transfer import Browser, STORE

DEEP="function all(r){return [...r.querySelectorAll('*')].flatMap(e=>[e,...(e.shadowRoot?all(e.shadowRoot):[])]);}"
INIT_CODE='''from pathlib import Path
import os, json
os.environ['WALTER_COLAB_CACHE_DIR']='/content/walter-cache-store'
p=Path(os.environ['WALTER_COLAB_CACHE_DIR'])
p.mkdir(exist_ok=True)
assert not p.is_symlink()
print('WALTER_MOUNT_FREE='+json.dumps({'store':str(p),'drive_mounted':os.path.ismount('/content/drive'),'google_credentials_present':Path('/content/google_token.json').exists(),'pid':os.getpid()}))
'''

def payload(result):
    if result.structured_content is not None:return result.structured_content
    return {'text':'\n'.join(i.text for i in result.content if hasattr(i,'text'))}

def source(cell):
    v=cell.get('source','')
    return ''.join(v) if isinstance(v,list) else v

def stream(cell):
    return ''.join(''.join(o.get('text',[])) if isinstance(o.get('text'),list) else o.get('text','')
        for o in cell.get('outputs',[]) if o.get('output_type')=='stream')

def parse_resources(lines):
    balance=[x for x in lines if re.fullmatch(r'Available: [0-9]+(?:\.[0-9]+)? compute units',x)]
    sessions=[x for x in lines if re.fullmatch(r'You have [0-9]+ active sessions\.',x)]
    rate=[x for x in lines if x.startswith('Usage rate:')]
    if len(balance)!=1 or len(sessions)!=1 or len(rate)!=1:
        raise RuntimeError('Live Colab resource fields missing or ambiguous')
    return {'compute_units':float(balance[0].split()[1]),
            'active_sessions':int(sessions[0].split()[2]),
            'balance_text':balance[0],'sessions_text':sessions[0],'rate_text':rate[0]}

class Bridge:
    def __init__(self,browser):
        self.browser=browser
        self.client=None
        self.owned={}

    def guard(self):
        if self.browser is not None:self.browser.assert_target()

    def open_browser(self,url):
        if '#' not in url:raise RuntimeError('Official MCP link fragment absent')
        fragment=url.split('#',1)[1]
        target='https://colab.research.google.com/drive/'+self.browser.notebook_id
        self.browser.action('/tab/navigate',url=target+'?walterMcp='+uuid.uuid4().hex+'#'+fragment)
        clicked=self.browser.evaluate('(async()=>{'+DEEP+'''
          const deadline=Date.now()+20000;
          while(Date.now()<deadline){
            const b=all(document).find(e=>e.tagName==='MD-TEXT-BUTTON'&&e.textContent.trim()==='Connect'&&e.getBoundingClientRect().width>0);
            if(b){(b.shadowRoot?.querySelector('button')||b).click();return true}
            await new Promise(r=>setTimeout(r,200));
          }return false})()''')
        if not clicked:raise RuntimeError('Official local MCP Connect approval missing')
        return True

    @asynccontextmanager
    async def connect(self):
        from fastmcp import Client, FastMCP
        from colab_mcp.session import ColabSessionProxy
        logging.disable(logging.CRITICAL)
        proxy=ColabSessionProxy()
        original=webbrowser.open_new
        try:
            webbrowser.open_new=self.open_browser
            await proxy.start_proxy_server()
            server=FastMCP(name='WalterMountFreeColab')
            server.mount(proxy.proxy_server)
            for middleware in proxy.middleware:server.add_middleware(middleware)
            async with Client(server) as client:
                self.client=client
                await client.call_tool('open_colab_browser_connection',{})
                if not proxy.wss.connection_live.is_set():raise RuntimeError('Official MCP connection not live')
                yield self
        finally:
            self.client=None
            webbrowser.open_new=original
            await proxy.cleanup()

    async def cells(self,outputs=False):
        self.guard()
        return payload(await self.client.call_tool('get_cells',{'includeOutputs':outputs}))['cells']

    async def set_code(self,cell_id,code):
        # Logical ownership survives Colab replacing a requested id with a random id.
        marker='# WALTER_CELL:'+cell_id+'\n'
        legacy='# WALTER_TRANSFER_CONTROL\n'
        cells=await self.cells()
        matches=[c for c in cells if c['id']==cell_id or source(c)==code or source(c).startswith(marker)]
        if len(matches)>1:raise RuntimeError('Ambiguous cell ownership; refusing automatic selection')
        if matches:
            old=matches[0]
            if source(old)!=code and not source(old).startswith(marker) and not (
                    code.startswith(legacy) and source(old).startswith(legacy)):
                raise RuntimeError('Refusing overwrite of a cell not owned by this controller')
            actual=code if source(old)==code or code.startswith(legacy) else marker+code
            cell_id=old['id']
            if source(old)!=actual:
                self.guard()
                await self.client.call_tool('update_cell',{'cellId':cell_id,'content':actual})
        else:
            actual=code if code.startswith(legacy) else marker+code
            self.guard()
            await self.client.call_tool('add_code_cell',{'cellIndex':len(cells),'language':'python','code':actual})
            matches=[c for c in await self.cells() if source(c)==actual]
            if len(matches)!=1:raise RuntimeError('Added control cell is ambiguous')
            cell_id=matches[0]['id']
        matches=[c for c in await self.cells() if c['id']==cell_id]
        if len(matches)!=1 or source(matches[0])!=actual:
            raise RuntimeError('MCP cell write readback mismatch')
        self.owned[cell_id]=actual
        return cell_id

    async def run(self,cell_id,timeout=240):
        cell=next(c for c in await self.cells() if c['id']==cell_id)
        if self.owned.get(cell_id)!=source(cell):
            raise RuntimeError('Refusing execution of unowned or changed control cell')
        self.guard()
        await asyncio.wait_for(self.client.call_tool('run_code_cell',{'cellId':cell_id}),timeout=timeout)
        cell=next(c for c in await self.cells(True) if c['id']==cell_id)
        if any(o.get('output_type')=='error' for o in cell.get('outputs',[])):
            raise RuntimeError('Colab code cell failed; inspect exact bound notebook, do not rerun blindly')
        return stream(cell)

    async def code(self,code,timeout=240):
        cells=await self.cells()
        marker='# WALTER_TRANSFER_CONTROL\n'
        old=[c for c in cells if source(c).startswith(marker)]
        if len(old)>1:raise RuntimeError('Ambiguous transfer control cells')
        cell=await self.set_code(old[0]['id'] if old else 'walter-transfer-control',marker+code)
        return await self.run(cell,timeout=timeout)

    async def initialize(self):
        cell=await self.set_code('cache-drive-mount',INIT_CODE)
        out=await self.run(cell)
        line=next(l for l in out.splitlines() if l.startswith('WALTER_MOUNT_FREE='))
        data=json.loads(line.split('=',1)[1])
        if data['store']!=STORE or data['google_credentials_present']:
            raise RuntimeError('Unexpected cache staging state')
        return data

    def runtime_menu(self):
        ok=self.browser.evaluate("(()=>{const e=document.querySelector('#runtime-menu-button');if(!e)return false;if(e.getAttribute('aria-expanded')!=='true'){for(const t of ['mousedown','mouseup'])e.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,button:0}));}return e.getAttribute('aria-expanded')==='true'})()")
        if not ok:raise RuntimeError('Runtime menu unavailable')

    def click_menu(self,name):
        point=self.browser.evaluate('(()=>{'+DEEP+f"const items=all(document).filter(e=>e.getAttribute('role')==='menuitem'&&e.textContent.trim()==={json.dumps(name)}&&e.getBoundingClientRect().width>0&&e.getAttribute('aria-disabled')!=='true');if(items.length!==1)return null;const r=items[0].getBoundingClientRect();return {{x:r.x+r.width/2,y:r.y+r.height/2}}"+'})()')
        if not point:raise RuntimeError('Exact Runtime control unavailable or ambiguous')
        # Closure highlights synthetic events without necessarily firing the command.
        # Native coordinates are derived from the unique live role/name, never guessed.
        self.browser.action('/tab/click-at',**point)

    def click_text(self,name):
        self.guard()
        ok=self.browser.evaluate('(()=>{'+DEEP+f"const a=all(document).filter(e=>e.tagName==='MD-TEXT-BUTTON'&&e.textContent.trim()==={json.dumps(name)}&&e.getBoundingClientRect().width>0&&!e.disabled);if(a.length!==1)return false;(a[0].shadowRoot?.querySelector('button')||a[0]).click();return true"+'})()')
        if not ok:raise RuntimeError('Exact dialog button unavailable or ambiguous')

    def resources(self):
        self.guard()
        read="const a=all(document).filter(e=>e.getBoundingClientRect().width>0&&e.children.length===0).map(e=>e.textContent.trim());const lines=[...new Set(a.filter(t=>t.startsWith('Available:')||t.startsWith('Usage rate:')||/^You have [0-9]+ active sessions\\./.test(t)))];"
        lines=self.browser.evaluate('(()=>{'+DEEP+read+'return lines})()')
        if lines:
            try:return parse_resources(lines)
            except RuntimeError:pass # The open panel can briefly expose a partial render.
        else:
            self.runtime_menu()
            self.click_menu('View resources')
        lines=self.browser.evaluate('(async()=>{'+DEEP+"const end=Date.now()+15000;while(Date.now()<end){"+read+"if(lines.some(t=>/^Available:/.test(t))&&lines.some(t=>/^Usage rate:/.test(t))&&lines.some(t=>/^You have [0-9]+ active sessions\\./.test(t)))return lines;await new Promise(r=>setTimeout(r,200));}return []})()")
        return parse_resources(lines)

    def runtime_choices(self):
        self.guard()
        self.runtime_menu()
        self.click_menu('Change runtime type')
        return self.browser.evaluate('(async()=>{'+DEEP+"const end=Date.now()+15000;while(Date.now()<end){const a=all(document).filter(e=>e.tagName==='MWC-RADIO'&&e.name==='accelerator'&&e.getBoundingClientRect().width>0);if(a.length)return a.map(e=>({value:e.value,checked:e.checked,disabled:e.disabled}));await new Promise(r=>setTimeout(r,200));}throw Error('Runtime choices missing')})()")

    def ensure_runtime_kind(self,device):
        values={'cpu':'','T4':'GPU,T4','L4':'GPU,L4','A100':'GPU,A100'}
        if device not in values:raise ValueError('Unsupported explicitly requested accelerator')
        if not self.runtime_state()['disconnected']:
            raise RuntimeError('Refusing to reconfigure an existing runtime')
        resources=self.resources()
        if resources['active_sessions']!=0:
            raise RuntimeError('Refusing allocation while another Colab session is active')
        if device!='cpu' and resources['compute_units']<=0:
            raise RuntimeError('No positive included unit balance; no paid purchase or free-worker fallback')
        choices=self.runtime_choices()
        matches=[r for r in choices if r['value']==values[device]]
        if len(matches)!=1 or matches[0]['disabled']:
            self.click_text('Cancel')
            raise RuntimeError('Requested accelerator unavailable; no silent fallback')
        if matches[0]['checked']:
            self.click_text('Cancel')
        else:
            ok=self.browser.evaluate('(()=>{'+DEEP+f"const a=all(document).filter(e=>e.tagName==='MWC-RADIO'&&e.name==='accelerator'&&e.value==={json.dumps(values[device])}&&!e.disabled&&e.getBoundingClientRect().width>0);if(a.length!==1)return false;(a[0].shadowRoot?.querySelector('input')||a[0]).click();return a[0].checked"+'})()')
            if not ok:
                self.click_text('Cancel')
                raise RuntimeError('Requested runtime radio selection not verified')
            self.click_text('Save')
            # Reopen the same live dialog and read back selection before allocation.
            verified=self.runtime_choices()
            self.click_text('Cancel')
            if sum(bool(r['checked'] and r['value']==values[device]) for r in verified)!=1:
                raise RuntimeError('Saved runtime accelerator readback failed')
        return {'selected':device,'disabled':False,'resources_before':resources}

    def released_state(self):
        deadline=time.monotonic()+20
        while True:
            state=self.runtime_state()
            resource=self.resources()
            if state['disconnected'] and resource['active_sessions']==0:
                return {**state,'resources_after':resource}
            if time.monotonic()>=deadline:
                raise RuntimeError('Runtime toolbar disconnected but allocated sessions remain; not released')
            time.sleep(.5)

    def delete_test_runtime(self):
        self.browser.assert_target()
        if self.runtime_state()['disconnected']:return self.released_state()
        self.runtime_menu()
        self.click_menu('Disconnect and delete runtime')
        deadline=time.monotonic()+30
        confirmed=False
        while time.monotonic()<deadline:
            state=self.runtime_state()
            if state['disconnected']:return self.released_state()
            if not confirmed:
                confirmed=self.browser.evaluate('(()=>{'+DEEP+"const bs=all(document).filter(e=>e.tagName==='MD-TEXT-BUTTON'&&['Yes','Disconnect and delete','Delete'].includes(e.textContent.trim())&&e.getBoundingClientRect().width>0);if(bs.length!==1)return false;const b=bs[0];(b.shadowRoot?.querySelector('button')||b).click();return true})()")
            time.sleep(.5)
        raise RuntimeError('Runtime deletion could not be verified')

    def runtime_state(self):
        return self.browser.evaluate('(()=>{'+DEEP+"const a=all(document).filter(e=>e.getBoundingClientRect().width>0);const labels=a.map(e=>e.getAttribute('aria-label')||'');const text=a.filter(e=>e.tagName==='MD-TEXT-BUTTON').map(e=>e.textContent.trim());return {disconnected:labels.some(s=>/Not connected to runtime|Click to connect/i.test(s))||text.some(s=>/^(Click to connect|Connect to a new runtime|Not connected to runtime)$/i.test(s)),buttons:text,connection:labels.filter(s=>/runtime|connect/i.test(s)).slice(0,15)}})()")

    def save_notebook(self):
        return self.browser.evaluate('(async()=>{await colab.global.notebook.saveNotebook();return true})()')
