# Bitwarden CLI Patterns

## Creating Items

The `bw create item` command requires base64-encoded JSON input via stdin:

```bash
bw get template item --session "$BW_SESSION" | python3 -c "
import sys, json, base64
item = json.load(sys.stdin)
item['name'] = 'Service Name'
item['login'] = {
    'username': 'user@example.com',
    'password': 'the_secret',
    'uris': [{'match': None, 'uri': 'https://service.com'}],
    'totp': None
}
item['fields'] = [{'name': 'extra_field', 'value': 'extra_value', 'type': 0}]
print(base64.b64encode(json.dumps(item).encode()).decode())
" | bw create item --session "$BW_SESSION" --raw
```

## Common Pitfalls

- **JSON parsing error**: `bw create item` expects base64-encoded input when using stdin, NOT raw JSON.
- **Session**: never run `bw unlock` yourself (it invalidates the session every Walter module shares). Use `walter-secret` (search / get / ref / exec), or `export BW_SESSION=$(~/.hermes/bin/bw-unlock --print)` when a raw `bw` command is unavoidable.
- **Template required**: Use `bw get template item` to get the correct item structure before modifying.
- **Type 1** = Login, **Type 2** = Secure Note, **Type 3** = Card, **Type 4** = Identity.
- **Fields type 0** = Text, **type 1** = Hidden (Boolean), **type 2** = Boolean.
