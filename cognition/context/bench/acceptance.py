"""Versioned, synthetic, offline retention acceptance. Never reads user history.

The predeclared gate is exact user and assistant text visibility, all tool
references, no input mutation and safe refusal. Visual understanding is not
silently counted as model-visible because logs exist.
This does not qualify model answer quality or activate the Hermes projection.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from walter_context import load
from walter_context.compress.checkpoint import summarize
from walter_context.compress.layers import record
from walter_context.compress.wire import tokens,text_of

VERSION='synthetic-retention-v1'
THRESHOLDS={'user_text_visibility':1.0,'assistant_text_visibility':1.0,'tool_reference_coverage':1.0,
            'expected_refusals':1.0,'input_mutation':0,'semantic_quality':'not_evaluated'}


def cases():
    def conversation(turns=6,tool_count=1):
        out=[{'role':'system','content':'Synthetic system head: preserve user constraints.'}]
        for t in range(turns):
            out.append({'role':'user','content':f'Turn {t}: keep /srv/example-{t} unchanged; never publish before approval.'})
            for k in range(tool_count):
                cid=f'call-{t}-{k}'
                out.extend([{'role':'assistant','content':'','tool_calls':[{'id':cid,'function':{'name':'read_file','arguments':'{"path":"/synthetic/input"}'}}]},
                            {'role':'tool','tool_call_id':cid,'content':'start '+('padding '*1200)+f' EXACT_TOOL_{t}_{k} '+('tail '*1200)}])
            out.append({'role':'assistant','content':f'Observed synthetic outcome {t}; this is historical evidence.'})
        return out
    yield {'id':'ordinary_tools','messages':conversation()}
    m=conversation();m[1]['content']='Préambule '+('contexte '*600)+'NE_JAMAIS_EFFACER_LA_BASE'+(' suite'*700)+' fin.'
    yield {'id':'middle_long_constraint','messages':m}
    m=conversation();m[1]['content']='最初の指示：個人情報を公開しない。 '+('事実 '*500)+'保持する制約 '+('محلي فقط '*100)+' FIN_CONTRAINTE_MULTILINGUE'
    yield {'id':'multilingual','messages':m}
    m=conversation();m[1]['content']='Earlier choice: retention is 7 days.';m[-4]['content']='Latest replacement decision: retention is now 30 days. The prior 7-day value is obsolete.'
    yield {'id':'superseding_decision','messages':m,'ordered':['retention is 7 days','retention is now 30 days']}
    m=conversation();m[2:2]=[{'role':'user','content':'Additional constraint in a consecutive user message: NO_UPLOAD.'}]
    yield {'id':'consecutive_user_messages','messages':m}
    m=conversation(2,18)
    yield {'id':'dense_tool_references','messages':m}
    m=conversation();m[1]['content']+='\n[file: {"id":"synthetic-document-A","uri":"synthetic://fixture/document.pdf"}]\n[image: {"id":"synthetic-image-B"}]'
    yield {'id':'normalized_attachment_refs','messages':m,'limits':['Attachment references retained, visual/audio content not understood or copied.']}
    m=conversation();gold='the replica lag exceeded 42 seconds'
    m[4]['content']='assistant prefix '+('x '*1000)+'The migration was postponed because '+gold+'. '+('y '*1000)
    yield {'id':'assistant_middle_explanation','messages':m,'observe':[gold],
           'question':'Why was the migration postponed?','gold':gold}
    m=conversation();gold='the checksum differed from the signed manifest'
    m[2]['content']='I stopped the deployment because '+gold+'.'
    yield {'id':'assistant_intermediate_explanation','messages':m,'observe':[gold],
           'question':'Why did the assistant stop the deployment before reading the next file?','gold':gold}
    m=conversation();m[4]['content']='Critical assistant explanation '+('must preserve '*1800)
    yield {'id':'oversized_assistant_text','messages':m,'budget':1600,'refusal':True}
    yield {'id':'small_host_budget','messages':conversation(3),'budget':500,'refusal':True}
    m=conversation();m[1]['content']='DO_NOT_TRUNCATE '+('mandatory instruction '*900)
    yield {'id':'oversized_user_constraints','messages':m,'budget':1600,'refusal':True}
    for role in ('system','developer'):
        m=conversation();m.insert(3,{'role':role,'content':'ROLE_INSTRUCTION_MUST_NOT_BE_FLATTENED'})
        yield {'id':'interleaved_'+role,'messages':m,'refusal':True}


def evaluate(case):
    messages=case['messages'];before=copy.deepcopy(messages)
    users=[text_of(m.get('content')).strip() for m in messages if m.get('role')=='user']
    assistants=[text_of(m.get('content')).strip() for m in messages if m.get('role')=='assistant' and text_of(m.get('content')).strip()]
    refs=[m['tool_call_id'] for m in messages if m.get('role')=='tool']
    began=time.perf_counter();result=None;refused=False
    try:result=summarize(messages,budget_tokens=case.get('budget',0))
    except ValueError:refused=True
    elapsed=(time.perf_counter()-began)*1000
    row={'id':case['id'],'input_tokens_estimate':tokens(messages),'latency_ms':round(elapsed,3),
         'expected_refusal':case.get('refusal',False),'refused':refused,'input_unchanged':messages==before}
    row['pass']=row['input_unchanged'] and refused==case.get('refusal',False)
    if result:
        content=result['content']
        repeat=summarize([{'role':'user','content':content},{'role':'assistant','content':'Synthetic continuation.'},
                          {'role':'user','content':'Keep the retained constraints.'}])['content']
        row.update(user_text_visible=sum(x in content for x in users),user_text_total=len(users),
                   assistant_text_visible=sum(x in content for x in assistants),assistant_text_total=len(assistants),
                   tool_refs_visible=sum(x in content for x in refs),tool_refs_total=len(refs),
                   user_text_visible_after_repeat=sum(x in repeat for x in users),
                   output_tokens_estimate=result['output_tokens'],
                   observed_detail_visibility={x:x in content for x in case.get('observe',[])})
        row['pass'] &= all(x in content and x in repeat for x in users) and all(x in content and x in repeat for x in refs)
        row['pass'] &= all(x in content and x in repeat for x in assistants)
        if case.get('question'):
            row['question']=case['question'];row['gold_answer_supported']=case['gold'] in content
            row['pass'] &= row['gold_answer_supported']
        if case.get('ordered'):row['pass'] &= [content.index(x) for x in case['ordered']]==sorted(content.index(x) for x in case['ordered'])
        # Compare the old capped record renderer to expose what the new invariant improves.
        baseline=record(messages[1:],load().projection,lambda m:text_of(m.get('content')))['content']
        row['legacy_record_user_text_visible']=sum(x in baseline for x in users)
    row['limitations']=case.get('limits',[])
    return row


def run():
    corpus=list(cases());rows=[evaluate(case) for case in corpus]
    positive=[r for r in rows if not r['refused']]
    return {'version':VERSION,'corpus_sha256':hashlib.sha256(json.dumps(corpus,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
            'thresholds_fixed_before_execution':THRESHOLDS,'case_count':len(rows),'passed':all(r['pass'] for r in rows),
            'rows':rows,'latency_p95_ms':sorted(r['latency_ms'] for r in rows)[int(.95*(len(rows)-1))],
            'total_input_tokens_estimate':sum(r['input_tokens_estimate'] for r in positive),
            'total_output_tokens_estimate':sum(r['output_tokens_estimate'] for r in positive),
            'provider_tokens_or_cache_measured':False,'external_model_calls':0,'provider_cost':0,
            'semantic_answer_quality':'not_evaluated','hermes_activation':'not_qualified',
            'known_limits':['Exact text retention does not prove model obedience or answer correctness.',
                            'Tool references require explicit recovery; full tool payloads are not model-visible by default.',
                            'Character-based token estimates are not provider token counts.',
                            'DSH role/transaction/recovery behavior is checked separately by its real host tests.']}


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--json',type=Path);a=parser.parse_args(argv)
    result=run()
    if a.json:a.json.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
