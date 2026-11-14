# CAPTCHA Solving for Browser Automation

## Technique #1: undetected-chromedriver + grecaptcha.execute() (FREE, preferred)

No paid service needed. Works for invisible reCAPTCHA v2 and v3.

```bash
pip install undetected-chromedriver selenium
apt-get install -y chromium-chromedriver  # ARM64
```

```python
import undetected_chromedriver as uc
import time, json, requests

options = uc.ChromeOptions()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--headless=new')
options.binary_location = '/usr/bin/chromium-browser'

driver = uc.Chrome(
    options=options,
    browser_executable_path='/usr/bin/chromium-browser',
    driver_executable_path='/usr/bin/chromedriver'
)

driver.get("https://target.com/register/")
time.sleep(10)

# Extract sitekey from iframe
sitekey = driver.execute_script("""
    for (const iframe of document.querySelectorAll('iframe')) {
        const m = (iframe.src||'').match(/k=([^&]+)/);
        if (m) return m[1];
    }
    return null;
""")

# Get valid token — no challenge shown, no human needed
token = driver.execute_script(f"""
    return new Promise((resolve) => {{
        grecaptcha.ready(function() {{
            grecaptcha.execute('{sitekey}', {{action: 'register'}}).then(resolve);
        }});
    }});
""")
# Returns: "0cAFcWeA7HzS8e_G2CWn..." (500+ chars)

# Submit token via API (faster than form filling)
cookies = {c['name']: c['value'] for c in driver.get_cookies()}
resp = requests.post(
    "https://target.com/api/register",
    json={"email": "...", "password": "...", "captcha": token},
    cookies=cookies,
    headers={"Referer": "https://target.com/register/"}
)
```

**Why this works**: `undetected-chromedriver` patches ChromeDriver to remove automation fingerprints. reCAPTCHA loads normally (not as invisible/headless). `grecaptcha.execute()` triggers the v3 scoring or v2 invisible path — both return valid tokens without user interaction.

**Limitations**: Doesn't work for reCAPTCHA v2 checkbox (visible challenge). For that, use capsolver or audio challenge.

## Technique #2: Paid Solvers

| Service | Free Trial | reCAPTCHA v2 | hCaptcha | Turnstile | API Endpoint |
|---------|-----------|-------------|----------|-----------|------|
| capsolver.com | $1 credit | yes | yes | yes | POST https://api.capsolver.com/createTask |
| 2captcha.com | ~$0.50 | yes | yes | yes | POST https://2captcha.com/in.php |
| anticaptcha.com | $0.50 | yes | yes | yes | REST API |
| nopecha.com | Free tier | yes | yes | no | Browser extension + API |

## Python Libraries

```bash
pip install 2captcha-python capsolver playwright-recaptcha
```

### capsolver (recommended)
```python
import capsolver
solution = capsolver.solve({
    "type": "ReCaptchaV2TaskProxyLess",
    "websiteURL": "https://site.com/page",
    "websiteKey": "6LfjEokU...",
})
token = solution['gRecaptchaResponse']
```

### 2captcha-python
```python
from twocaptcha import TwoCaptcha
solver = TwoCaptcha('YOUR_API_KEY')
result = solver.recaptcha(sitekey='6LfjEokU...', url='https://site.com/page')
token = result['code']
```

### playwright-recaptcha (free, audio challenge, unreliable)
```python
from playwright_recaptcha import SyncSolverV2
solver = SyncSolverV2(page)
token = solver.solve_recaptcha()
```
Often fails: can't locate reCAPTCHA in iframes, audio challenge rate-limited.

## Injecting Solved Token

```python
page.evaluate("""(token) => {
    const textarea = document.getElementById('g-recaptcha-response');
    if (textarea) textarea.value = token;
    if (typeof ___grecaptcha_cfg !== 'undefined') {
        Object.entries(___grecaptcha_cfg.clients).forEach(([key, client]) => {
            const find = (obj) => {
                for (let k in obj) {
                    if (typeof obj[k] === 'function' && k.length < 3) {
                        try { obj[k](token); } catch(e) {}
                    }
                    if (typeof obj[k] === 'object' && obj[k]) find(obj[k]);
                }
            };
            find(client);
        });
    }
}""", token)
```

## Sitekey Extraction

```python
sitekey = page.evaluate("""() => {
    const div = document.querySelector('.g-recaptcha, .h-captcha, [data-sitekey]');
    if (div) return div.getAttribute('data-sitekey');
    for (const iframe of document.querySelectorAll('iframe')) {
        const match = (iframe.src || '').match(/k=([^&]+)/);
        if (match) return match[1];
    }
    return null;
}""")
```

## Chicken-and-Egg Problem

CAPTCHA solving services have CAPTCHAs on their own signup:
- capsolver.com: Cloudflare Turnstile
- 2captcha.com: reCAPTCHA
- anticaptcha.com: CAPTCHA

Workaround: Use Playwright CDP browser to register (may pass Turnstile). If blocked, ask user to register manually.

## Escape Hatches (try in order)

1. Check for REST API (bypasses CAPTCHA entirely)
2. Check for Google/GitHub OAuth (often no CAPTCHA)
3. Use capsolver/2captcha paid service
4. Audio challenge (free, unreliable)
5. Ask user for 30-second manual action
