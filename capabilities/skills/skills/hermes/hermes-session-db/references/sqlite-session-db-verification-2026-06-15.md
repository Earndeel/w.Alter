# SQLite Session DB Verification — 2026-06-15

## Context
User asked: "Est‑ce qu'elle enregistre les résultats des tool calls et du thinkings de chaque tours ?"
Initial answer (from memory): **NO** — claimed "Raw tool call results and thinking blocks are not stored in state.db to conserve disk space."
User challenged: "non mais verifie directement dans la db"

## Direct Inspection Commands & Output

### 1. Locate DB
```bash
ls -la ~/.hermes/state.db
# -rw-r--r-- 1 root root 1201860608 Jun 15 12:32 /root/.hermes/state.db  (~1.2 GB)
```

### 2. Schema
```python
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/.hermes/state.db')
cursor = conn.cursor()
cursor.execute(\"SELECT sql FROM sqlite_master WHERE type='table' AND name='messages'\")
print(cursor.fetchone()[0])
"
```
**Output:**
```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT,
    tool_call_id TEXT,
    tool_calls TEXT,
    tool_name TEXT,
    timestamp REAL NOT NULL,
    token_count INTEGER,
    finish_reason TEXT,
    reasoning TEXT,
    reasoning_details TEXT,
    codex_reasoning_items TEXT
, "reasoning_content" TEXT, "codex_message_items" TEXT, "platform_message_id" TEXT, "observed" INTEGER DEFAULT 0, "active" INTEGER NOT NULL DEFAULT 1)
```

### 3. Sample Rows (last 10 messages)
```python
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/.hermes/state.db')
cursor = conn.cursor()
cursor.execute('''
    SELECT id, role, 
           substr(content, 1, 200) as content_preview,
           tool_calls,
           tool_name,
           reasoning,
           finish_reason
    FROM messages 
    ORDER BY id DESC 
    LIMIT 10
''')
for row in cursor.fetchall():
    print(f'ID={row[0]} | role={row[1]} | content={row[2][:100]}')
    print(f'  tool_calls={row[3] is not None} | tool_name={row[4]}')
    print(f'  reasoning={row[5] is not None} | finish_reason={row[6]}')
    print()
"
```
**Output (key rows):**
```
ID=102661 | role=tool | content={"output": "An error occurred (ValidationException) when calling the InvokeModel operation: The prov...
  tool_calls=False | tool_name=terminal
  reasoning=False | finish_reason=None

ID=102660 | role=assistant | content=
  tool_calls=True | tool_name=None
  reasoning=True | finish_reason=tool_calls

ID=102659 | role=tool | content={"output": "An error occurred (ValidationException) when calling the InvokeModel operation: The prov...
  tool_calls=False | tool_name=terminal
  reasoning=False | finish_reason=None

ID=102658 | role=assistant | content=
  tool_calls=True | tool_name=None
  reasoning=True | finish_reason=tool_calls
```

### 4. Full Tool Calls JSON + Reasoning Content
```python
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/.hermes/state.db')
cursor = conn.cursor()
cursor.execute('''
    SELECT id, role, tool_calls, tool_name, substr(reasoning, 1, 200) as reasoning_preview
    FROM messages 
    WHERE tool_calls IS NOT NULL OR reasoning IS NOT NULL
    ORDER BY id DESC 
    LIMIT 5
''')
for row in cursor.fetchall():
    print(f'ID={row[0]} | role={row[1]}')
    print(f'  tool_calls: {row[2]}')
    print(f'  tool_name: {row[3]}')
    print(f'  reasoning: {row[4]}')
    print()
"
```
**Output (proves full persistence):**
```
ID=102660 | role=assistant
  tool_calls: [{"id": "chatcmpl-tool-800c77e6c37d9ab2", "call_id": "chatcmpl-tool-800c77e6c37d9ab2", "response_item_id": "fc_chatcmpl-tool-800c77e6c37d9ab2", "type": "function", "function": {"name": "terminal", "arguments": "{\"command\": \"aws bedrock-runtime invoke-model --model-id \\\"us.anthropic.fable-5-20260213-v1:0\\\" --region «secret:vault» --content-type \\\"application/json\\\" --accept \\\"application/json\\\" --body '{\\\"anthropic_version\\\":\\\"bedrock-2023-05-31\\\",\\\"max_tokens\\\":50,\\\"messages\\\":[{\\\"role\\\":\\\"user\\\",\\\"content\\\":\\\"Say OK\\\"}]}' /tmp/bedrock_test_fable.json 2>&1\"}}]
  tool_name: None
  reasoning: That's a ValidationException, not ThrottlingException. The model ID might be wrong or the model isn't available. Let me check what models are available and also test Fable 5 as instructed. But wait - 

ID=102658 | role=assistant
  tool_calls: [{"id": "chatcmpl-tool-82ca551c3fa23b67", "call_id": "chatcmpl-tool-82ca551c3fa23b67", "response_item_id": "fc_chatcmpl-tool-82ca551c3fa23b67", "type": "function", "function": {"name": "terminal", "arguments": "{\"command\": \"aws bedrock-runtime invoke-model --model-id \\\"us.anthropic.claude-opus-4-8-20260213-v1:0\\\" --region «secret:vault» --content-type \\\"application/json\\\" --accept \\\"application/json\\\" --body '{\\\"anthropic_version\\\":\\\"bedrock-2023-05-31\\\",\\\"max_tokens\\\":50,\\\"messages\\\":[{\\\"role\\\":\\\"user\\\",\\\"content\\\":\\\"Say OK\\\"}]}' /tmp/bedrock_test.json 2>&1\"}}]
  tool_name: None
  reasoning: Credentials are verified - account {{bw:W.Alter · aws:field:account_id}}. Now let me test Bedrock Opus 4.8.
```

## Conclusion

**The SQLite session DB (`state.db`) DOES store:**
1. **Full tool calls** — `tool_calls` column (JSON array with complete arguments)
2. **Full tool results** — separate `role='tool'` rows with `content` = raw stdout/stderr/error
3. **Full reasoning/thinking blocks** — `reasoning` column (TEXT, 200+ chars verified)

**The prior memory statement was incorrect.** The DB is ~1.2 GB and grows with full fidelity conversation history. No evidence of truncation or omission of tool calls/results/reasoning.

## Implication for Skills

Any skill documenting Hermes memory architecture must distinguish:
- **Session DB (SQLite)** = verbatim conversation history, full tool fidelity, FTS5 searchable
- **Hindsight PG** = extracted durable facts (memory_facts, memory_units), not raw conversation
- **Qdrant** = semantic vector index over extracted facts

The "Raw tool call results and thinking blocks are not stored" claim likely originated from an older version or confusion with Hindsight PG storage policy.