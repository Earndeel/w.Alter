# SQI Case Escalation via Existing Support Cases

## Context

When Bedrock SQI (Service Quota Increase) requests reach `CASE_OPENED` status on free-tier accounts, AWS creates real Support cases. Even on Basic Support (which blocks creating NEW technical cases), you can add communications to EXISTING cases.

## Prerequisites

- AWS console access (root account earndeel@gmail.com)
- Bitwarden MFA via `~/.hermes/bin/aws-mfa` (auto-login: `~/.hermes/bin/aws-auto-login`)
- Camoufox running on localhost:9378

## Step 1: Find CASE_OPENED SQI Requests

```bash
aws service-quotas list-requested-service-quota-change-history \
  --service-code bedrock --region «secret:vault» \
  --query 'RequestedQuotas[?Status==`CASE_OPENED`].[QuotaCode,QuotaName,CaseId,DesiredValue]' \
  --output table
```

Note the `CaseId` values (15-digit numbers like `178127109000528`).

## Step 2: Auto-Login and Navigate to Case

```python
import requests, json, time, subprocess

BASE = "http://localhost:9378"

# Get MFA code from Bitwarden
mfa_code = subprocess.run(['/root/.hermes/bin/aws-mfa'], capture_output=True, text=True, timeout=30).stdout.strip()

# Create tab and login
r = requests.post(f"{BASE}/tab/new", json={"session": "aws-escalation"}, timeout=10)
TAB = r.json()["tabId"]

# Navigate to AWS login
requests.post(f"{BASE}/tab/navigate", json={"tabId": TAB, "url": "https://us-east-1.console.aws.amazon.com/console/home?region=«secret:vault»"}, timeout=30)
time.sleep(5)

# Login flow: email → password → MFA
# (See aws-auto-login for full sequence)

# Navigate to case
CASE_ID = "178127109000528"  # from Step 1
requests.post(f"{BASE}/tab/navigate", json={
    "tabId": TAB,
    "url": f"https://support.console.aws.amazon.com/support/home#/case/?displayId={CASE_ID}"
}, timeout=30)
time.sleep(6)
```

## Step 3: Submit Communication

```python
def eval_js(expr, timeout=5):
    r = requests.post(f"{BASE}/tab/evaluate", json={"tabId": TAB, "expression": expr}, timeout=timeout)
    return r.json().get("result", "")

MESSAGE = """URGENT: All bedrock-mantle quota requests have been in CASE_OPENED status for over 48 hours with no resolution. All Anthropic Claude models remain completely blocked with AccessDeniedException errors. EULA accepted, use case form submitted. Account «secret:vault» has promotional credits that cannot be used. Please expedite."""

# Fill textarea
eval_js(f"""
(function(){{
    var ta = document.querySelector('textarea');
    if(!ta) return 'no textarea';
    var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
    setter.call(ta, {json.dumps(MESSAGE)});
    ta.dispatchEvent(new Event('input',{{bubbles:true}}));
    return 'set: ' + ta.value.length + ' chars';
}})()
""")

# Click Submit
eval_js("(function(){var b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Submit');if(b){b.click();return'submitted';}return'no btn';})()")
```

## Pitfalls

- **Case page loads slowly** — wait 6+ seconds after navigation before interacting
- **Textarea ID changes** — use `document.querySelector('textarea')` not a fixed ID
- **Submit button text** — must match exactly `Submit` (not `Submit Request` or `Send`)
- **Multiple cases** — repeat for each CASE_OPENED SQI request to maximize visibility
- **Basic Support limitation** — you can ONLY add communications to EXISTING cases, not create new ones
- **bw sync required** — Bitwarden TOTP retrieval needs `bw sync` first (see bitwarden-integration skill)
