"""Real fresh-CPU-runtime recovery proof; affects only the bound private test notebook."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import time
import uuid
from bridge import Bridge,source
from drive_store import DriveStore
from run import bootstrap_code,report_from_output,runtime_hash_code
from transfer import Browser

ROOT=Path('/opt/walter-colab')
CONFIG=json.loads((ROOT/'config.json').read_text())
NOTE='''# W.Alter — cache privé sans montage Drive

Transfert réel : Drive privé → VM W.Alter → interface Fichiers Colab → `/content/walter-cache-store`, et retour vérifié par SHA256.
L'authentification Drive reste sur la VM W.Alter : aucun refresh token transmis au notebook et aucun `drive.mount()`.
Le disque local disparaît à la suppression du runtime ; les objets privés Drive persistent.

L'agent utilise `/opt/walter-colab/run.py` avec `stage`, `bootstrap` et `persist` ; les cellules sont pilotées par le MCP officiel Google Colab.
Ce notebook est configuré sur CPU pour vérifier les transferts. La cellule de contrôle GPU est réservée à une future exécution GPU explicitement demandée.

Validé : transport binaire et rechargement des scripts dans un runtime neuf, sans dialogue de montage Drive.
Non validé ici : archive complète des dépendances Qwen/ComfyUI, gain de temps de restauration et nouvelle inférence GPU.
Aucun achat ni keep-alive ; les limites normales de Colab s'appliquent.
'''

async def main():
    assert not CONFIG['new_purchase_allowed']
    store=DriveStore(CONFIG['drive_folder_id'])
    def saved():return json.loads(store.service.files().get_media(fileId=CONFIG['notebook_id']).execute())
    old=saved()
    assert old.get('metadata',{}).get('accelerator') in (None,''),'CPU-only test refuses a GPU-selected notebook'
    backup=Path('/root/.hermes/backups/colab')/('pre-fresh-recovery-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.ipynb')
    backup.parent.mkdir(parents=True,exist_ok=True)
    backup.write_text(json.dumps(old,ensure_ascii=False))
    backup.chmod(0o600)
    browser=Browser(CONFIG['browser_session'],CONFIG['notebook_id'])
    bridge=Bridge(browser)
    sentinel='/content/walter-session-'+uuid.uuid4().hex+'.json'
    report={'utc':datetime.now(timezone.utc).isoformat(),'notebook_id':CONFIG['notebook_id'],'drive_folder_id':CONFIG['drive_folder_id'],'backup':str(backup),'no_new_purchase':True,'transport_objects':[]}
    async with bridge.connect():
        await bridge.initialize()
        out=await bridge.code('import torch,json\nfrom pathlib import Path\np=Path('+repr(sentinel)+')\nassert not torch.cuda.is_available()\np.write_text("current-test-runtime")\nprint("WALTER_SENTINEL="+json.dumps({"created":p.is_file(),"gpu_available":torch.cuda.is_available()}))')
        report['old_runtime']=report_from_output(out,'WALTER_SENTINEL=')
        assert report['old_runtime']=={'created':True,'gpu_available':False}
        await bridge.set_code('instructions',NOTE)
        assert bridge.save_notebook()
        current=saved()
        assert ''.join(next(c for c in current['cells'] if (c.get('id') or c.get('metadata',{}).get('id'))=='instructions')['source'])==NOTE
        report['first_runtime_deleted']=bridge.delete_test_runtime()['disconnected']
        assert report['first_runtime_deleted']
    fresh=Bridge(browser)
    try:
        async with fresh.connect():
            out=await fresh.code('import torch,json\nfrom pathlib import Path\nassert not torch.cuda.is_available()\nprint("WALTER_FRESH="+json.dumps({"old_sentinel_absent":not Path('+repr(sentinel)+').exists(),"old_store_absent":not Path("/content/walter-cache-store").exists(),"gpu_available":torch.cuda.is_available()}))')
            report['fresh_runtime']=report_from_output(out,'WALTER_FRESH=')
            assert report['fresh_runtime']=={'old_sentinel_absent':True,'old_store_absent':True,'gpu_available':False}
            report['fresh_state']=await fresh.initialize()
            assert not report['fresh_state']['drive_mounted']
            assert not report['fresh_state']['google_credentials_present']
            scratch=Path('/root/.hermes/cache/scratch/colab-no-mount');scratch.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='fresh-proof-',dir=scratch) as tmp:
                for name in ['cache_runtime.py','walter-qwen-inference.py','walter-transport-binary-test.bin']:
                    path=Path(tmp)/name
                    expected=store.fetch(name,path)
                    upload=browser.upload(path)
                    actual=report_from_output(await fresh.code(runtime_hash_code(name)),'WALTER_FILE=')
                    assert actual['sha256']==expected['sha256'] and actual['size_bytes']==expected['size_bytes']
                    receipt={'name':name,'drive':expected,'runtime':actual,'upload_seconds':upload['seconds']}
                    if name.endswith('.bin'):
                        back=Path(tmp)/'return'/name
                        receipt['runtime_download']=browser.download(name,back,expected_sha256=expected['sha256'])
                        receipt['drive_return']=store.save(back)
                        assert receipt['drive_return']['id']==expected['id']
                    report['transport_objects'].append(receipt)
            code=bootstrap_code()
            before=sum(source(c)==code for c in await fresh.cells())
            cell=await fresh.set_code('walter-cache-bootstrap',code)
            report['bootstrap']=report_from_output(await fresh.run(cell),'WALTER_BOOTSTRAP=')
            assert report['bootstrap']['cache_module_imported']
            assert report['bootstrap']['dependency_cache_archive_present'] is False
            after=sum(source(c)==code for c in await fresh.cells())
            assert before==after==1, 'Repeated bootstrap must reuse its real notebook cell id'
            report['idempotent_bootstrap_cell']=True
            assert fresh.save_notebook()
            d=saved()
            cells=d['cells']
            assert ''.join(next(c for c in cells if (c.get('id') or c.get('metadata',{}).get('id'))=='instructions')['source'])==NOTE
            init=next(c for c in cells if (c.get('id') or c.get('metadata',{}).get('id'))=='cache-drive-mount')
            assert 'drive.mount(' not in ''.join(init['source'])
            boot=next(c for c in cells if ''.join(c['source'])==code)
            outputs=''.join(''.join(o.get('text',[])) for o in boot.get('outputs',[]) if o.get('output_type')=='stream')
            assert report_from_output(outputs,'WALTER_BOOTSTRAP=')==report['bootstrap']
            report['exact_drive_notebook_readback_verified']=True
    finally:
        if not fresh.runtime_state()['disconnected']:
            report['final_runtime_state']=fresh.delete_test_runtime()
    assert fresh.runtime_state()['disconnected']
    report['completed_utc']=datetime.now(timezone.utc).isoformat()
    (ROOT/'fresh-runtime-proof.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
