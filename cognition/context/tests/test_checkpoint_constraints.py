from dataclasses import replace
import pytest
from walter_context.checkpoint import summarize
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

def test_over_budget_preservation_is_refused_not_truncated():
 text='must preserve this sentence '*500
 with pytest.raises(ValueError,match='preserve user constraints'):
  summarize([{'role':'user','content':text}],budget_tokens=1000)

def test_all_tool_references_survive_action_summary_limit():
 messages=[{'role':'user','content':'do the analysis'}]
 for i in range(30):
  messages.extend([{'role':'assistant','tool_calls':[{'id':f'tool-{i}','function':{'name':'read','arguments':'{}'}}]},
                   {'role':'tool','tool_call_id':f'tool-{i}','content':'x'*8000}])
 result=summarize(messages)['content']
 assert all(f'tool-{i}' in result for i in range(30))
