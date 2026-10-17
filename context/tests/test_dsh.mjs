import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createRequire} from 'node:module';
import {WalterContextEngine, bridge, normalize, recoverOwn} from '../ports/dsh/index.mjs';
const require = createRequire(process.env.WALTER_DSH_PACKAGE || '/opt/dsh/package.json');
const {Context} = require('@deepseek-ai/cordis');
const {Session} = require('@deepseek-ai/dsh-session');
const {ToolRuntime} = require('@deepseek-ai/dsh-tools');
const {createUserMessage,createAssistantMessage,createToolResultMessage,createSystemMessage,createDeveloperMessage} = require('@deepseek-ai/dsh-llm');

function setup() {
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
  ctx.provide('llm', {resolveModelInfo:async () => ({context:{contextWindow:200000}})});
  const engine = new WalterContextEngine(ctx,{auto:false});
  const agent = {session, options:{provider:'walter',model:'coding'},
    runMaintenance: fn => fn(new AbortController().signal)};
  session.append('request/header',{reason:'initial',header:{config:{provider:'walter',model:'coding'}}});
  return {ctx,session,engine,agent,registered};
}
function fill(session, turns = 5, instructionRole = null) {
  for (let t=0;t<turns;t++) {
    session.append('turn/start',{turn:t});
    session.append('user/message',createUserMessage({content:[{type:'text',text:`request ${t}`}],source:{kind:'user'}}),{surfaceOp:'append'});
    if (t === 1 && instructionRole) {
      const message = instructionRole === 'system' ? createSystemMessage('CRITICAL_ROLE_INSTRUCTION') :
        createDeveloperMessage({content:[{type:'text',text:'CRITICAL_ROLE_INSTRUCTION'}],source:{kind:'fixture'}});
      session.append(`${instructionRole}/message`,{message},{surfaceOp:'append'});
    }
    session.append('assistant/message',{turn:t,step:0,stream:[],message:createAssistantMessage({content:[{type:'tool-call',id:`call-${t}`,name:'read_file',arguments:'{}'}],source:{provider:'walter',model:'coding'}})},{surfaceOp:'append'});
    session.append('tool/result',{turn:t,step:0,message:createToolResultMessage({callId:`call-${t}`,content:[{type:'text',text:`evidence-${t} `+'z'.repeat(60000)}],isError:false})},{surfaceOp:'append'});
    session.append('assistant/message',{turn:t,step:1,stream:[],message:createAssistantMessage({content:[{type:'text',text:`answer ${t}`}],source:{provider:'walter',model:'coding'}})},{surfaceOp:'append'});
    session.append('turn/end',{turn:t,reason:{kind:'completed'}});
  }
  session.append('turn/start',{turn:turns});
  session.append('user/message',createUserMessage({content:[{type:'text',text:'latest live request'}],source:{kind:'user'}}),{surfaceOp:'append'});
}

test('real DSH transaction: Walter checkpoint, raw originals, replay and recovery', async () => {
  const {session,engine,agent,registered} = setup();
  session.append('system/message',{message:createSystemMessage('PRESERVED_GLOBAL_HEAD')},{surfaceOp:'append'});
  fill(session);
  const before = Array.from({length:session.seq},(_,n)=>session.eventAt(n));
  const live = session.deriveMessages().slice(-5);
  const result = await engine.compactIfNeeded(agent,'pressure',new AbortController().signal);
  assert.ok(result);
  assert.deepEqual(Array.from({length:before.length},(_,n)=>session.eventAt(n)),before);
  assert.deepEqual(session.deriveMessages().slice(-5),live);
  assert.equal(session.deriveMessages()[0].content[0].text,'PRESERVED_GLOBAL_HEAD');
  const summary = session.eventAt(result.summarySeq);
  assert.equal(summary.data.provider,'walter-context');
  assert.equal(summary.data.model,'extractive-v1');
  assert.ok(summary.data.summary[0].text.includes('call-0'));
  assert.equal(registered[0].name,'context_recover');
  const original = recoverOwn(session,'call-0');
  assert.match(original.content,/evidence-0/); assert.equal(original.next_offset,12000);
  assert.match(recoverOwn(session,'missing').error,/No tool result/);
  const events = Array.from({length:session.seq},(_,n)=>session.eventAt(n));
  const replay = Session.create(session.id,events);
  assert.deepEqual(replay.deriveMessages(),session.deriveMessages());
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
