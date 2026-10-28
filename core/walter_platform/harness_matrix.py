"""Read-only capability matrix: configuration is not runtime or quality proof."""
from __future__ import annotations
import datetime
import hashlib
import json
from pathlib import Path
from . import harness,registry
from .composition import COMPOSITIONS,definition

CAPABILITIES=('identity','memory','logs','skills','secrets','browse','computer','model','context')
MODULE={'identity':'soul','model':'llm',**{x:x for x in CAPABILITIES if x not in ('identity','model')}}


def _file_evidence(path):
    path=Path(path)
    return {'path':str(path),'present':path.is_file(),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


QUALIFICATION_MAX_AGE_DAYS=14


def _scenario_qualifications():
    """Latest passing end-to-end scenario per harness:capability (walter-scenario, P6 2026-10-28), recent only."""
    try:
        from . import instance
        data=json.loads(Path(instance.state('scenarios','qualifications.json')).read_text())
    except (OSError,ValueError,ImportError,AttributeError):
        return {}
    out={}
    limit=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=QUALIFICATION_MAX_AGE_DAYS)
    for key,q in data.get('pairs',{}).items():
        try:
            at=datetime.datetime.strptime(q['at'],'%Y%m%dT%H%M%SZ').replace(tzinfo=datetime.timezone.utc)
        except (KeyError,ValueError):
            continue
        if at>=limit:out[key]={**q,'evidence':'walter-scenario run '+q['scenario']+' (assertions on the recorded run)'}
    return out


def matrix():
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    qualifications=_scenario_qualifications()
    evidence_path=COMPOSITIONS/'observations.json'
    evidence=json.loads(evidence_path.read_text()) if evidence_path.exists() else {'observations':[]}
    modules={x['id']:x for x in registry.load()['modules']}
    rows=[]
    for host in harness.HOSTS:
        spec=definition(host);data,path=harness.read(host);state=harness.check(host)
        hp=harness.default_home(host);bindings=state['bindings'];mcp=state['common_mcp']
        identity=Path(spec['identity_source']) if spec['identity_scope']=='workspace' else hp/('SOUL.md' if host=='hermes' else 'AGENTS.md')
        plugins=set(bindings.get('plugins',[]))-set(data.get('plugins',{}).get('disabled',[])) if host=='hermes' else set()
        expected={'memory':'walter-memory','skills':'walter-skills','secrets':'walter-secrets','browse':'walter-browse','computer':'walter-computer-use','logs':'walter-logs'}
        for capability in CAPABILITIES:
            module=modules.get(MODULE[capability],{})
            anchors=module.get('anchors',[])
            available=bool(anchors) and all(Path(x).exists() for x in anchors)
            provider=MODULE[capability];limits=[];refs=[_file_evidence(path)]
            if capability=='identity':
                bound=identity.is_file();refs.append(_file_evidence(identity))
                if spec['identity_scope']=='workspace':limits.append('Identity applies only when the session loads this profile cwd; current-session identity is not inferred.')
            elif capability=='model':
                if host=='dsh':bound=bool(bindings.get('model_route'));provider='walter-llm'
                else:bound=False;provider='native';limits.append('Principal model remains selected by this harness; module-specific Walter model calls are separate.')
            elif capability=='context':
                if host=='dsh':bound=bool(bindings.get('context_plugin'));provider='walter-context/checkpoint';limits.append('Deterministic retention/transaction qualified; semantic model-answer quality is not established.')
                elif host=='hermes':bound=False;provider=bindings.get('context_engine');limits.append('Hermes native compressor until walter-context replaces it (walter-context plan, lot 6).')
                else:bound=False;provider='native';limits.append('Native compaction is not replaceable through the supported MCP interface.')
            elif capability=='logs':
                bound='walter-logs' in plugins if host=='hermes' else bool(bindings.get('lifecycle_hook'))
                limits.append('Only exposed source traces can be archived; watcher/connector health must be checked separately.')
            elif host=='hermes':
                bound=expected[capability] in plugins
                if capability=='memory':
                    provider=bindings.get('memory_provider')
                    selected=hp/'plugins'/str(provider)/'__init__.py'
                    bound=provider=='walter-memory' and provider not in data.get('plugins',{}).get('disabled',[]) and selected.is_file()
                    refs.append(_file_evidence(selected))
                    limits.append('Provider plugin selected; canonical/privacy migration and live reload require their own proof.')
            else:bound=mcp
            runtime=host.replace('-','_')
            observations=[o for o in evidence.get('observations',[]) if o['runtime']==runtime and o['capability']==capability]
            used=True if observations else None
            if host=='codex':limits.append('Nested tools inside exec are not individually attributed by the current log metadata; lack of evidence is not non-use.')
            refs.extend(observations)
            qualified=qualifications.get(f'{host}:{capability}')
            if qualified:used=True
            rows.append({'harness':host,'capability':capability,'module':MODULE[capability],
                         'available':available,'bound':bound,'in_use':used,'qualified':qualified,
                         'provider':provider,'verification_at':now,'evidence':refs,'limitations':limits,
                         'qualification_scope':'Full end-to-end capability acceptance pending; unit/contract tests are separate evidence.'})
    return {'version':1,'generated_at':now,'ok':True,'read_only':True,
            'definitions':{'available':'Declared module anchors are present locally.',
                           'bound':'Configuration selects a Walter port/surface, with stated scope; process reload is not inferred.',
                           'in_use':'A dated historical interface invocation/ingestion was observed; success or current revision is not inferred. Null means unknown.',
                           'qualified':'A recent (14 days) passing end-to-end scenario on real traces for the stated scope (walter-scenario qualifies:); null means not demonstrated.'},
            'observation_snapshot_at':evidence.get('generated_at'),'bindings':rows}
