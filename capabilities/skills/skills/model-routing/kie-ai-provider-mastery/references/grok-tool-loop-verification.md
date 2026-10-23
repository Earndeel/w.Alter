# Kie.ai Grok 4.6 — verified function-calling loop

## Scope

Direct API evidence for a two-turn custom-function loop. This is a protocol verification fixture, not a weather report: the tool result below was generated locally and deterministically.

## Endpoint and headers

```text
POST https://api.kie.ai/grok/v1/responses
Authorization: Bearer <KIE_API_KEY>
Content-Type: application/json
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/135 Safari/537.36
Accept: text/event-stream
```

## Turn 1 — request a structured call

```json
{
  "model": "grok-4-6",
  "stream": true,
  "input": [{
    "role": "user",
    "content": [{
      "type": "input_text",
      "text": "Use the get_current_weather function now for Bangkok, Thailand. The function call must be emitted as a structured tool call, not described in prose."
    }]
  }],
  "tools": [{
    "type": "function",
    "name": "get_current_weather",
    "description": "Get the current weather in a location.",
    "parameters": {
      "type": "object",
      "properties": {
        "location": {"type": "string"},
        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
      },
      "required": ["location", "unit"],
      "additionalProperties": false
    }
  }],
  "tool_choice": {"type": "function", "name": "get_current_weather"},
  "parallel_tool_calls": false,
  "max_output_tokens": 200,
  "reasoning": {"effort": "low"},
  "store": false
}
```

### Required SSE evidence

Do not infer a tool call from prose. The verified stream contained:

```text
event: response.output_item.added
item.type = function_call
item.call_id = call-aeaeaa4b-a39a-400e-ad8a-560ab74e8e1b-0
item.name = get_current_weather
item.arguments = ""

event: response.function_call_arguments.delta
data.delta = {"location":"Bangkok, Thailand","unit":"celsius"}

event: response.function_call_arguments.done
data.arguments = {"location":"Bangkok, Thailand","unit":"celsius"}

event: response.output_item.done
item.type = function_call
item.status = completed
```

The `response.completed` payload repeated the completed function call and reported `credits_consumed: 0.11`, `reasoning_tokens: 117`, and `num_server_side_tools_used: 0`. The custom function was client-side; Kie did not execute it.

## Local tool execution and Turn 2

The client executed the function locally and sent:

```json
{
  "type": "function_call",
  "id": "fc_34140673-fc4b-9d5e-bb9a-3ff89fb57a30_0",
  "call_id": "call-aeaeaa4b-a39a-400e-ad8a-560ab74e8e1b-0",
  "name": "get_current_weather",
  "arguments": "{\"location\":\"Bangkok, Thailand\",\"unit\":\"celsius\"}"
}
```

Then:

```json
{
  "type": "function_call_output",
  "call_id": "call-aeaeaa4b-a39a-400e-ad8a-560ab74e8e1b-0",
  "output": "{\"location\":\"Bangkok, Thailand\",\"unit\":\"celsius\",\"temperature_c\":31,\"condition\":\"partly cloudy\"}"
}
```

The exact returned `call_id` (`call-...`) was accepted unchanged by Grok. The second response was HTTP 200, cost `0.05` credit, and returned visible text `31°C, partly cloudy.` with no additional tool call.

## Interpretation guardrails

- This proves transport, structured function-call emission, argument streaming, client-side tool-result round trip, and final grounding for Grok 4.6 through Kie.
- It does not prove that Kie itself executed the function: the client executed the local mock.
- It does not prove Hermes runtime routing. For Hermes, capture the actual outbound URL/body and billing metadata separately.
- `num_server_side_tools_used: 0` is expected here; it is not evidence that custom tools are unsupported.
- Kie documentation states web search and custom function tools are mutually exclusive on this endpoint.

## Failed probe worth avoiding

A separate test used `tool_choice: "required"` and a prose-only instruction. The model returned a long textual description of an intended call and no structured function-call events. Treat that as a probe-design failure, not as a provider capability verdict; use the explicit function selector and inspect SSE event types.
