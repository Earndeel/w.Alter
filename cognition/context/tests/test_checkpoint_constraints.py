from dataclasses import replace
import pytest
from walter_context.compress.checkpoint import summarize
from walter_context import load

@pytest.mark.parametrize('role', ['system', 'developer'])
def test_in_history_instructions_refused_without_mutating_input(role):
 from copy import deepcopy
 messages=[{'role':'system','content':'head stays in host'},
           {'role':'user','content':'initial request'},
           {'role':role,'content':'CRITICAL_ROLE_INSTRUCTION'},
           {'role':'assistant','content':'answer'}]
 before=deepcopy(messages)
 with pytest.raises(ValueError,match='in-history system/developer'):
  summarize(messages)
 assert messages == before

def test_entire_user_constraint_survives_repeated_checkpoint():
 text='prefix '+('x '*1000)+'KEEP_MIDDLE_CONSTRAINT'+('y '*1000)+' tail'
 body=[{'role':'user','content':text},{'role':'assistant','content':'short answer'},
       {'role':'tool','tool_call_id':'ref-1','content':'output '*4000}]
 first=summarize(body)['content']
 assert text in first
 second=summarize([{'role':'user','content':first},{'role':'user','content':'followup'},
                   {'role':'tool','tool_call_id':'ref-2','content':'more '*4000}])['content']
 assert text in second and 'ref-1' in second and 'ref-2' in second

def test_over_budget_owner_text_is_kept_whole_never_refused_or_truncated():
 # 2026-11-11: a record past its share is bounded, not refused (a long session could no longer compact at all).
 # The owner's words are never clipped; the host still checks that the replacement is smaller than the span.
 text='must preserve this sentence '*500
 result=summarize([{'role':'user','content':text}],budget_tokens=1000)
 assert ' '.join(text.split()) in result['content'] and result['brief_turns']==1 and result['omitted_turns']==0

def test_long_history_is_bounded_oldest_turns_first_with_an_explicit_note():
 messages=[]
 for i in range(60):
  messages += [{'role':'user','content':f'request {i} '+'detail '*200},{'role':'assistant','content':f'answer {i} '+'text '*400}]
 result=summarize(messages,budget_tokens=20000)
 assert result['output_tokens'] <= 20000*load().policy.record_share+50   # the estimate of entry sizes is approximate
 assert result['omitted_turns']>0 and 'earlier turns omitted' in result['content']
 assert 'request 59' in result['content'] and 'request 0 ' not in result['content']

def test_injected_user_messages_and_earlier_record_do_not_pose_as_owner_text():
 messages=[{'role':'user','src':'compact-checkpoint','content':'[Session record: earlier] - old request'},
           {'role':'user','src':'agent-instructions','content':'AGENTS_FILE_BODY'},
           {'role':'user','src':'user','content':'real request'},
           {'role':'user','src':'walter-intake','content':'<walter-context>\nPACK_BODY\n</walter-context>'},
           {'role':'assistant','content':'real answer'}]
 content=summarize(messages)['content']
 assert 'AGENTS_FILE_BODY' not in content and 'PACK_BODY' not in content
 assert content.index('old request') < content.index('real request') < content.index('real answer')
 assert '## User\n[Session record' not in content

def test_all_tool_references_survive_action_summary_limit():
 messages=[{'role':'user','content':'do the analysis'}]
 for i in range(30):
  messages.extend([{'role':'assistant','tool_calls':[{'id':f'tool-{i}','function':{'name':'read','arguments':'{}'}}]},
                   {'role':'tool','tool_call_id':f'tool-{i}','content':'x'*8000}])
 result=summarize(messages)['content']
 assert all(f'tool-{i}' in result for i in range(30))

def test_all_visible_assistant_explanations_survive_in_order_and_repeat():
 explanation='prefix '+('x '*1000)+'REPLICA_LAG_EXCEEDED_42_SECONDS'+('y '*1000)+' end'
 intermediate='Stopped because checksum differed from the signed manifest.'
 messages=[{'role':'user','content':'investigate'},
           {'role':'assistant','content':explanation},
           {'role':'assistant','content':intermediate,'reasoning_content':'PRIVATE_REASONING',
            'tool_calls':[{'id':'check','function':{'name':'read','arguments':'{}'}}]},
           {'role':'tool','tool_call_id':'check','content':'output '*4000},
           {'role':'assistant','content':'Final answer.'}]
 first=summarize(messages)['content']
 assert first.index(explanation)<first.index(intermediate)<first.index('Final answer.')
 assert 'PRIVATE_REASONING' not in first
 second=summarize([{'role':'user','content':first},{'role':'assistant','content':'Followup.'}])['content']
 assert explanation in second and intermediate in second

def test_oversized_assistant_text_goes_to_one_line_with_the_request_whole():
 result=summarize([{'role':'user','content':'explain'},
                   {'role':'assistant','content':'mandatory explanation '*1000}],budget_tokens=1000)
 assert '- explain → mandatory explanation' in result['content'] and result['brief_turns']==1

def test_tool_without_recoverable_reference_refused():
 with pytest.raises(ValueError,match='lacks a recoverable reference'):
  summarize([{'role':'user','content':'analyse'}, {'role':'tool','content':'important evidence'}])
