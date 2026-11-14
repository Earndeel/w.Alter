import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createRequire} from 'node:module';
import {WalterContextEngine, bridge, normalize, recoverOwn} from '../ports/dsh/index.mjs';
const require = createRequire(process.env.WALTER_DSH_PACKAGE || '/opt/dsh/package.json');
const {Context} = require('@deepseek-ai/cordis');
const {Session} = require('@deepseek-ai/dsh-session');
const {ToolRuntime} = require('@deepseek-ai/dsh-tools');
const {createUserMessage,createAssistantMessage,createToolResultMessage,createSystemMessage,createDeveloperMessage} = require('@deepseek-ai/dsh-llm');

function setup(contextWindow = 60000) {   // below the engine profile's 96k: these fixtures must be under pressure
  const ctx = new Context();
  const session = Session.create('walter-context-test');
  ctx.provide('systemPrompt', {tools: () => {}});
  const tools = new ToolRuntime(ctx);
  const registered = [];
  const register = tools.register.bind(tools);
  tools.register = tool => { registered.push(tool); return register(tool); };
  ctx.provide('sessions', {flush: async () => {}});
  // Use the real DSH surface and durable transaction with a deterministic meter.
  // Production retains DSH's singleton meter; this keeps tests provider-free.
  const price = m => Math.ceil(JSON.stringify(m.content).length / 4);
  ctx.provide('tokenMeter', {estimateMessage:price, measure:s => {
    const nodes = s.surface.nodes.map(seq => ({seq, tokens:price(s.deriveEventMessage(s.eventAt(seq))),
      heuristicTokens:price(s.deriveEventMessage(s.eventAt(seq)))}));
    return {nodes, totalTokens:nodes.reduce((s,n)=>s+n.tokens,0)};
  }});
  ctx.provide('llm', {resolveModelInfo:async () => ({context:{contextWindow}})});
  const engine = new WalterContextEngine(ctx,{auto:false});
  const agent = {session, options:{provider:'walter',model:'coding'},
    runMaintenance: fn => fn(new AbortController().signal)};
  session.append('request/header',{reason:'initial',header:{config:{provider:'walter',model:'coding'}}});
  return {ctx,session,engine,agent,registered};
}
function fill(session, turns = 5, instructionRole = null, startTurn = 0) {
  for (let t=startTurn;t<startTurn+turns;t++) {
    session.append('turn/start',{turn:t});
    session.append('user/message',createUserMessage({content:[{type:'text',text:`request ${t}`}],source:{kind:'user'}}),{surfaceOp:'append'});
    if (t === 1 && instructionRole) {
      const message = instructionRole === 'system' ? createSystemMessage('CRITICAL_ROLE_INSTRUCTION') :
        createDeveloperMessage({content:[{type:'text',text:'CRITICAL_ROLE_INSTRUCTION'}],source:{kind:'fixture'}});
      session.append(`${instructionRole}/message`,{message},{surfaceOp:'append'});
    }
    session.append('assistant/message',{turn:t,step:0,stream:[],message:createAssistantMessage({content:[{type:'tool-call',id:`call-${t}`,name:'read_file',arguments:'{}'}],source:{provider:'walter',model:'coding'}})},{surfaceOp:'append'});
    session.append('tool/result',{turn:t,step:0,message:createToolResultMessage({callId:`call-${t}`,content:[{type:'text',text:`evidence-${t} `+'z'.repeat(30000)+` MIDDLE_TOOL_EVIDENCE_${t} `+'z'.repeat(30000)}],isError:false})},{surfaceOp:'append'});
    session.append('assistant/message',{turn:t,step:1,stream:[],message:createAssistantMessage({content:[{type:'text',text:`answer ${t}`}],source:{provider:'walter',model:'coding'}})},{surfaceOp:'append'});
    session.append('turn/end',{turn:t,reason:{kind:'completed'}});
  }
  session.append('turn/start',{turn:startTurn+turns});
  session.append('user/message',createUserMessage({content:[{type:'text',text:'latest live request'}],source:{kind:'user'}}),{surfaceOp:'append'});
}

test('real DSH transaction: Walter checkpoint, raw originals, replay and recovery', async () => {
  const {session,engine,agent,registered} = setup();
  session.append('system/message',{message:createSystemMessage('PRESERVED_GLOBAL_HEAD')},{surfaceOp:'append'});
  fill(session);
  const before = Array.from({length:session.seq},(_,n)=>session.eventAt(n));
  const live = session.deriveMessages().slice(-1);
  const result = await engine.compactIfNeeded(agent,'pressure',new AbortController().signal);
  assert.ok(result);
  assert.deepEqual(Array.from({length:before.length},(_,n)=>session.eventAt(n)),before);
  // under pressure every completed turn is folded from its originals (window policy); the live turn is untouched
  assert.deepEqual(session.deriveMessages().slice(-1),live);
  assert.equal(session.deriveMessages().length,3);
  assert.equal(session.deriveMessages()[0].content[0].text,'PRESERVED_GLOBAL_HEAD');
  const summary = session.eventAt(result.summarySeq);
  assert.equal(summary.data.provider,'walter-context');
  assert.equal(summary.data.model,'window-v1');
  assert.ok(summary.data.summary[0].text.includes('call-0'));
  assert.ok(summary.data.summary[0].text.includes('## User\nrequest 4') && summary.data.summary[0].text.includes('answer 4'));
  assert.equal(registered[0].name,'context_recover');
  const original = recoverOwn(session,'call-0');
  assert.match(original.content,/evidence-0/); assert.equal(original.next_offset,12000);
  assert.match(recoverOwn(session,'missing').error,/No tool result/);
  const events = Array.from({length:session.seq},(_,n)=>session.eventAt(n));
  const replay = Session.create(session.id,events);
  assert.deepEqual(replay.deriveMessages(),session.deriveMessages());
});

test('repeated real checkpoints retain old user constraints and recover middle tool evidence', async () => {
  const {session,engine,agent} = setup();
  const text='Initial constraint '+('context '.repeat(1600))+' KEEP_MIDDLE_USER_CONSTRAINT '+('tail '.repeat(900))+' end';
  session.append('user/message',createUserMessage({content:[{type:'text',text}],source:{kind:'user'}}),{surfaceOp:'append'});
  fill(session);
  assert.ok(await engine.compactIfNeeded(agent,'pressure',new AbortController().signal));
  assert.ok(JSON.stringify(session.deriveMessages()).includes('KEEP_MIDDLE_USER_CONSTRAINT'));
  session.append('turn/end',{turn:5,reason:{kind:'completed'}});
  fill(session,5,null,6);
  assert.ok(await engine.compactIfNeeded(agent,'pressure',new AbortController().signal));
  // The record is bounded ([relevance] record_budget_tokens): a 5k-token request from ten turns ago either stays whole
  // or leaves with an explicit note, never silently and never clipped; the journal keeps it either way.
  const surface=JSON.stringify(session.deriveMessages());
  assert.ok(surface.includes('KEEP_MIDDLE_USER_CONSTRAINT') || surface.includes('earlier turns are not shown here'));
  assert.ok(!surface.includes('KEEP_MIDDLE_USER_CONSTRAINT') || session.deriveMessages().some(m=>m.content.some(b=>b.type==='text'&&b.text.replace(/\s+/g,' ').includes(text.replace(/\s+/g,' ').trim()))));   // whole, whitespace folded on a one-line entry
  assert.ok(Array.from({length:session.seq},(_,n)=>session.eventAt(n)).some(e=>e.type==='user/message'&&JSON.stringify(e.data).includes('KEEP_MIDDLE_USER_CONSTRAINT')));
  assert.ok(surface.includes('request 10'));
  let offset=0,full='';
  do {
    const page=recoverOwn(session,'call-0',offset);full+=page.content;offset=page.next_offset;
  } while(offset!==null);
  assert.ok(full.includes('MIDDLE_TOOL_EVIDENCE_0'));
  const events=Array.from({length:session.seq},(_,n)=>session.eventAt(n));
  assert.deepEqual(Session.create(session.id,events).deriveMessages(),session.deriveMessages());
});

test('multimodal normalization keeps durable attachment references without pretending visual retention', () => {
  const m=normalize([{role:'user',content:[{type:'text',text:'Read the attachment.'},
    {type:'file',attachment:{id:'synthetic-pdf',uri:'synthetic://fixture/document.pdf'}},
    {type:'image',attachment:{id:'synthetic-image'}}]}])[0];
  assert.match(m.content,/synthetic-pdf/);assert.match(m.content,/synthetic-image/);
  assert.match(m.content,/synthetic:\/\/fixture\/document.pdf/);
});

test('failed Python bridge closes the bracket without changing the surface', async () => {
  const {session,engine,agent} = setup(); fill(session);
  const before = session.deriveMessages();
  engine.summarize = async () => {throw new Error('bridge unavailable');};
  await assert.rejects(engine.compactIfNeeded(agent,'pressure',new AbortController().signal),/bridge unavailable/);
  assert.deepEqual(session.deriveMessages(),before);
  assert.equal(session.eventAt(session.seq-1).type,'compaction/end');
  assert.match(session.eventAt(session.seq-1).data.error,/bridge unavailable/);
});

test('in-history system/developer instructions refuse compaction and preserve the surface', async () => {
  for (const role of ['system','developer']) {
    const {session,engine,agent} = setup(); fill(session,5,role);
    const before = session.deriveMessages();
    await assert.rejects(engine.compactIfNeeded(agent,'pressure',new AbortController().signal),/system\/developer/);
    assert.deepEqual(session.deriveMessages(),before);
    assert.equal(session.eventAt(session.seq-1).type,'compaction/end');
    assert.equal(Array.from({length:session.seq},(_,n)=>session.eventAt(n)).some(e=>e.type==='compaction/summary'),false);
    assert.ok(session.deriveMessages().some(m=>m.role===role&&m.content.some(b=>b.text==='CRITICAL_ROLE_INSTRUCTION')));
  }
});

test('privileged role at the beginning of a compactRegion span is refused', async () => {
  for (const role of ['system','developer']) {
    const {session,engine,agent} = setup();
    session.append('system/message',{message:createSystemMessage('PRESERVED_GLOBAL_HEAD')},{surfaceOp:'append'});
    session.append('user/message',createUserMessage({content:[{type:'text',text:'earlier request'}],source:{kind:'user'}}),{surfaceOp:'append'});
    const message = role === 'system' ? createSystemMessage('LEADING_ROLE_INSTRUCTION') :
      createDeveloperMessage({content:[{type:'text',text:'LEADING_ROLE_INSTRUCTION'}],source:{kind:'fixture'}});
    const start = session.append(`${role}/message`,{message},{surfaceOp:'append'}).seq;
    fill(session);
    const before = session.deriveMessages();
    const end = session.surface.nodes.at(-2);
    await assert.rejects(engine.compactRegion(start,end,agent,new AbortController().signal),/system\/developer/);
    assert.deepEqual(session.deriveMessages(),before);
    assert.equal(session.eventAt(session.seq-1).type,'compaction/end');
    assert.equal(Array.from({length:session.seq},(_,n)=>session.eventAt(n)).some(e=>e.type==='compaction/summary'),false);
  }
});

test('manual compactNow refuses a leading developer after the retained system head', async () => {
  const {session,engine,agent} = setup();
  session.append('system/message',{message:createSystemMessage('PRESERVED_GLOBAL_HEAD')},{surfaceOp:'append'});
  session.append('developer/message',{message:createDeveloperMessage({content:[{type:'text',text:'LEADING_DEVELOPER_INSTRUCTION'}],source:{kind:'fixture'}})},{surfaceOp:'append'});
  fill(session);
  session.append('turn/end',{turn:5,reason:{kind:'completed'}});
  const before = session.deriveMessages();
  await assert.rejects(engine.compactNow(agent,new AbortController().signal),/manual compaction could not produce/);
  assert.deepEqual(session.deriveMessages(),before);
  assert.equal(session.eventAt(session.seq-1).type,'compaction/end');
  assert.equal(Array.from({length:session.seq},(_,n)=>session.eventAt(n)).some(e=>e.type==='compaction/summary'),false);
});

test('abort does not compact, and concurrent compaction is rejected by DSH lock', async () => {
  const {session,engine,agent} = setup(); fill(session);
  const aborted = new AbortController(); aborted.abort();
  const before = session.seq;
  await assert.rejects(engine.compactIfNeeded(agent,'pressure',aborted.signal));
  assert.equal(session.seq,before);
  const nodes = session.surface.nodes;
  const running = engine.compactRegion(nodes[0],nodes[11],agent,new AbortController().signal);
  await assert.rejects(engine.compactRegion(nodes[0],nodes[11],agent,new AbortController().signal),/already in progress/);
  await running;
});

test('bridge fails closed on unsupported protocol, preserves full input', async () => {
  const messages=[{role:'user',content:'request'},{role:'assistant',content:'answer'}];
  const before=structuredClone(messages);
  const result=await bridge({op:'summarize',messages});
  assert.match(result.content,/Historical reference only/);
  assert.deepEqual(messages,before);
  await assert.rejects(bridge({op:'unknown',messages}),/bridge exited/);
  assert.throws(()=>normalize([{role:'user',content:[{type:'future-unknown'}]}]),/unsupported/);
});

test('a live turn over budget is trimmed by the host pruner on Walter\'s decision, originals recoverable', async () => {
  const {ctx,session,engine,agent} = setup();
  const {ToolResultPruner} = require('@deepseek-ai/dsh-compaction-tool-result-pruner');
  new ToolResultPruner(ctx,{thresholdChars:8192,headChars:4096,tailChars:1024});
  await new Promise(r=>setTimeout(r,0));
  session.append('turn/start',{turn:0});
  session.append('user/message',createUserMessage({content:[{type:'text',text:'deep research'}],source:{kind:'user'}}),{surfaceOp:'append'});
  for (let s=0;s<40;s++) {   // one live turn, 40 pages read: nothing before it to checkpoint (2026-11-07 overflow)
    session.append('assistant/message',{turn:0,step:s,stream:[],message:createAssistantMessage({content:[{type:'tool-call',id:`page-${s}`,name:'walter_browse',arguments:'{}'}],source:{provider:'walter',model:'coding'}})},{surfaceOp:'append'});
    session.append('tool/result',{turn:0,step:s,message:createToolResultMessage({callId:`page-${s}`,content:[{type:'text',text:`HEAD-${s} `+'p'.repeat(20000)+` PAGE_MIDDLE_${s} `+'p'.repeat(20000)}],isError:false})},{surfaceOp:'append'});
  }
  const before = ctx.tokenMeter.measure(session).totalTokens;
  assert.equal(await engine.compactIfNeeded(agent,'pressure',new AbortController().signal), null);
  const after = ctx.tokenMeter.measure(session).totalTokens;
  assert.ok(after < before / 4, `${after} vs ${before}`);
  const text = JSON.stringify(session.deriveMessages());
  assert.ok(text.includes('HEAD-39') && !text.includes('PAGE_MIDDLE_39'));
  let offset=0,full='';
  do { const page=recoverOwn(session,'page-39',offset); full+=page.content; offset=page.next_offset; } while(offset!==null);
  assert.ok(full.includes('PAGE_MIDDLE_39'));
});

test('below budget nothing is trimmed', async () => {
  const {ctx,session,engine,agent} = setup();
  const {ToolResultPruner} = require('@deepseek-ai/dsh-compaction-tool-result-pruner');
  new ToolResultPruner(ctx,{}); await new Promise(r=>setTimeout(r,0));
  session.append('turn/start',{turn:0});
  session.append('user/message',createUserMessage({content:[{type:'text',text:'one page'}],source:{kind:'user'}}),{surfaceOp:'append'});
  session.append('assistant/message',{turn:0,step:0,stream:[],message:createAssistantMessage({content:[{type:'tool-call',id:'p',name:'walter_browse',arguments:'{}'}],source:{provider:'walter',model:'coding'}})},{surfaceOp:'append'});
  session.append('tool/result',{turn:0,step:0,message:createToolResultMessage({callId:'p',content:[{type:'text',text:'x'.repeat(30000)+' KEEP_ALL'}],isError:false})},{surfaceOp:'append'});
  const before = JSON.stringify(session.deriveMessages());
  assert.equal(await engine.compactIfNeeded(agent,'pressure',new AbortController().signal), null);
  assert.equal(JSON.stringify(session.deriveMessages()), before);
});

// --- window of an owner turn (decision A1, 2026-11-11) ---------------------------------------------------------------
const DAY = 86_400_000;
function completedTurn(session, t, {thread = null, toolChars = 60000, request = `request ${t}`} = {}) {
  session.append('turn/start',{turn:t});
  session.append('user/message',createUserMessage({content:[{type:'text',text:request}],source:{kind:'user'}}),{surfaceOp:'append'});
  session.append('user/message',createUserMessage({content:[{type:'text',text:`AGENT_INSTRUCTIONS_${t} `+'i'.repeat(3000)}],source:{kind:'agent-instructions'}}),{surfaceOp:'append'});
  session.append('user/message',createUserMessage({content:[{type:'text',text:`<walter-context>\nSTALE_PACK_${t} `+'p'.repeat(4000)+'\n</walter-context>'}],
    source:{kind:'walter-intake',...(thread?{thread}:{})}}),{surfaceOp:'append'});
  session.append('assistant/message',{turn:t,step:0,stream:[],message:createAssistantMessage({content:[{type:'tool-call',id:`call-${t}`,name:'memory_events',arguments:'{}'}],source:{provider:'walter',model:'coding'}})},{surfaceOp:'append'});
  session.append('tool/result',{turn:t,step:0,message:createToolResultMessage({callId:`call-${t}`,content:[{type:'text',text:`TOOL_PAYLOAD_${t} `+'z'.repeat(toolChars)}],isError:false})},{surfaceOp:'append'});
  session.append('assistant/message',{turn:t,step:1,stream:[],message:createAssistantMessage({content:[{type:'text',text:`answer ${t}`}],source:{provider:'walter',model:'coding'}})},{surfaceOp:'append'});
  session.append('turn/end',{turn:t,reason:{kind:'completed'}});
}
const text = session => JSON.stringify(session.deriveMessages());

test('window: a message arriving the next day enters a session reduced to what its thread needs', async () => {
  const {ctx,session,engine,agent} = setup(200000);
  session.append('system/message',{message:createSystemMessage('PRESERVED_GLOBAL_HEAD')},{surfaceOp:'append'});
  completedTurn(session,1,{thread:'subject:voice'}); completedTurn(session,2,{thread:'subject:other'});
  completedTurn(session,3,{thread:'subject:voice'});
  const before = ctx.tokenMeter.measure(session).totalTokens;
  const journalBefore = Array.from({length:session.seq},(_,n)=>session.eventAt(n));
  session.append('turn/start',{turn:4});            // the engine's pre-step: the turn is open, its message not yet in
  // the engine's intake is outside the host's isolated compaction group: it reaches the window by its published entry
  const entry = globalThis[Symbol.for('walter.context.window')];
  assert.equal(typeof entry,'function');
  const report = await entry(agent,{plan:{thread:'subject:voice'},now:Date.now()+DAY},new AbortController().signal);
  assert.equal(report.applied,true); assert.equal(report.reason,'cold_cache');
  assert.deepEqual(report.turns,{verbatim:0,full:2,brief:1,omitted:0,leaving:3});
  const after = ctx.tokenMeter.measure(session).totalTokens;
  assert.ok(before > 45000 && after < 600, `${before} -> ${after}`);
  const surface = text(session);
  assert.equal(session.deriveMessages().length,2);
  assert.ok(surface.includes('PRESERVED_GLOBAL_HEAD') && surface.includes('## User\\nrequest 3') && surface.includes('answer 1'));
  assert.ok(surface.includes('request 2 → answer 2'));                       // the other thread: one line
  for (const gone of ['STALE_PACK','AGENT_INSTRUCTIONS','TOOL_PAYLOAD']) assert.ok(!surface.includes(gone), gone);
  assert.ok(surface.includes('ref call-3'));
  assert.match(recoverOwn(session,'call-3').content,/TOOL_PAYLOAD_3/);       // originals stay recoverable
  assert.deepEqual(Array.from({length:journalBefore.length},(_,n)=>session.eventAt(n)),journalBefore);
  const events=Array.from({length:session.seq},(_,n)=>session.eventAt(n));
  assert.deepEqual(Session.create(session.id,events).deriveMessages(),session.deriveMessages());
  // nothing new to gain: the same boundary is not rewritten
  const again = await engine.window(agent,{plan:{thread:'subject:voice'},now:Date.now()+DAY},new AbortController().signal);
  assert.equal(again.applied,false);
});

test('window: levels are recomputed from the journal originals, never from the previous record', async () => {
  const {session,engine,agent} = setup(200000);
  session.append('system/message',{message:createSystemMessage('PRESERVED_GLOBAL_HEAD')},{surfaceOp:'append'});
  completedTurn(session,1,{thread:'subject:a'}); completedTurn(session,2,{thread:'subject:b'});
  session.append('turn/start',{turn:3});
  assert.equal((await engine.window(agent,{plan:{thread:'subject:b'},now:Date.now()+DAY},new AbortController().signal)).applied,true);
  assert.ok(text(session).includes('request 1 → answer 1') && text(session).includes('## User\\nrequest 2'));
  session.append('user/message',createUserMessage({content:[{type:'text',text:'request 3'}],source:{kind:'user'}}),{surfaceOp:'append'});
  session.append('assistant/message',{turn:3,step:0,stream:[],message:createAssistantMessage({content:[{type:'tool-call',id:'call-3',name:'read',arguments:'{}'}],source:{provider:'walter',model:'coding'}})},{surfaceOp:'append'});
  session.append('tool/result',{turn:3,step:0,message:createToolResultMessage({callId:'call-3',content:[{type:'text',text:'z'.repeat(60000)}],isError:false})},{surfaceOp:'append'});
  session.append('assistant/message',{turn:3,step:1,stream:[],message:createAssistantMessage({content:[{type:'text',text:'answer 3'}],source:{provider:'walter',model:'coding'}})},{surfaceOp:'append'});
  session.append('turn/end',{turn:3,reason:{kind:'completed'}});
  session.append('turn/start',{turn:4});
  // the owner comes back to thread a two days later: its first turn is rendered in full again, from the journal
  const report = await engine.window(agent,{plan:{thread:'subject:a'},now:Date.now()+2*DAY},new AbortController().signal);
  assert.equal(report.applied,true);
  const surface = text(session);
  assert.equal(session.deriveMessages().length,2);
  assert.ok(surface.includes('## User\\nrequest 1') && surface.includes('request 2 → answer 2') && surface.includes('request 3 → answer 3'));
  assert.equal(surface.split('Session record:').length,2);                  // one record, not a record of a record
});

test('window: a live exchange keeps its last small turn verbatim and its warm cache', async () => {
  const {session,engine,agent} = setup(200000);
  session.append('system/message',{message:createSystemMessage('PRESERVED_GLOBAL_HEAD')},{surfaceOp:'append'});
  completedTurn(session,1,{thread:'subject:a',toolChars:2000});
  session.append('turn/start',{turn:2});
  const before = text(session);
  const report = await engine.window(agent,{plan:{thread:'subject:a'}},new AbortController().signal);
  assert.equal(report.applied,false); assert.equal(report.reason,'nothing_to_replace'); assert.equal(report.warm,true);
  assert.equal(report.turns.verbatim,1);
  assert.equal(text(session),before);
});

test('window: a surface holding a privileged message is left to the host', async () => {
  const {session,engine,agent} = setup(200000);
  session.append('system/message',{message:createSystemMessage('PRESERVED_GLOBAL_HEAD')},{surfaceOp:'append'});
  completedTurn(session,1);
  session.append('developer/message',{message:createDeveloperMessage({content:[{type:'text',text:'CRITICAL_ROLE_INSTRUCTION'}],source:{kind:'fixture'}})},{surfaceOp:'append'});
  completedTurn(session,2);
  session.append('turn/start',{turn:3});
  const report = await engine.window(agent,{now:Date.now()+DAY},new AbortController().signal);
  assert.equal(report.applied,false); assert.equal(report.reason,'irregular_surface');
  assert.ok(text(session).includes('CRITICAL_ROLE_INSTRUCTION'));
});
