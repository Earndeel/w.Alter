# Usage Data Path Fix

## Problem

The script `skill_quality_audit.py` looks for usage data at:
```
~/.hermes/skill-usage.json
```

But the actual path in current Hermes is:
```
~/.hermes/skills/.usage.json
```

## Fix

In `skill_quality_audit.py`, change:
```python
USAGE_DB = HERMES_HOME / "skill-usage.json"
```
to:
```python
USAGE_DB = HERMES_HOME / "skills" / ".usage.json"
```

## Verification

```bash
ls -la ~/.hermes/skills/.usage.json
python3 << 'EOF'
import json
from pathlib import Path
p = Path.home() / ".hermes" / "skills" / ".usage.json"
print(p.exists())
EOF
```
