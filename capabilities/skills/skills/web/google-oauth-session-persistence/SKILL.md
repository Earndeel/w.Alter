---
name: google-oauth-session-persistence
category: devops
description: Maintain persistent Google login sessions in headless Chrome for automating Google OAuth flows on third-party services. Eliminates human-in-the-loop for "Continue with Google" buttons.
---

## Trigger
When a service uses Google OAuth ("Continue with Google") and you need to authenticate programmatically without user interaction.

## Core Insight
Google OAuth consent requires an authenticated Google session in the browser. If the Chrome profile has an active Google session, "Continue with Google" buttons auto-approve without any user interaction.

## Architecture

```
Persistent Chrome Profile (~/.hermes/chrome-profiles/google-main)
    ↓ contains Google session cookies
undetected-chromedriver (--user-data-dir=...)
    ↓ navigates to service
Service → "Continue with Google" → Google (already logged in) → auto-approve → callback
```

## Setup (One-Time)

### Step 1: Create persistent profile
```bash
mkdir -p ~/.hermes/chrome-profiles/google-main
```

### Step 2: Initial Google login (requires user once)
Option A — via CDP + noVNC desktop:
```bash
bash ~/.hermes/scripts/start-chrome-google.sh
# User accesses desktop, logs into Google
```

Option B — via undetected-chromedriver (sends auth URL to user):
```python
import undetected_chromedriver as uc
options = uc.ChromeOptions()
options.add_argument('--no-sandbox')
options.add_argument('--headless=new')
options.add_argument('--user-data-dir=/root/.hermes/chrome-profiles/google-main')
options.binary_location = '/usr/bin/chromium-browser'

driver = uc.Chrome(options=options,
    browser_executable_path='/usr/bin/chromium-browser',
    driver_executable_path='/usr/bin/chromedriver')

driver.get("https://accounts.google.com/signin")
# Send driver.current_url to user via Telegram
# User completes sign-in on their device
# Session cookies are saved to persistent profile
```

### Step 3: Verify session persists
```python
# In a new session, using same profile:
driver.get("https://myaccount.google.com/")
time.sleep(5)
if "Sign in" not in driver.find_element(By.TAG_NAME, "body").text:
    print("Google session active!")
```

## Usage Pattern (After Setup)

```python
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time

options = uc.ChromeOptions()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--headless=new')
options.add_argument('--user-data-dir=/root/.hermes/chrome-profiles/google-main')
options.add_argument('--profile-directory=Default')
options.binary_location = '/usr/bin/chromium-browser'

driver = uc.Chrome(options=options,
    browser_executable_path='/usr/bin/chromium-browser',
    driver_executable_path='/usr/bin/chromedriver')

# Navigate to service
driver.get("https://service.com/register/")
time.sleep(10)

# Click "Continue with Google"
google_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Continue with Google')]")
driver.execute_script("arguments[0].click()", google_btn)
time.sleep(8)

# Google auto-approves because session is active
# Service receives auth callback → user is logged in

# Now interact with service (get API keys, etc.)
driver.get("https://service.com/account/api")
time.sleep(5)
api_key = driver.execute_script("return document.querySelector('.api-key')?.textContent")
```

## Extracting API Keys After OAuth

Once logged in via Google OAuth:
1. Navigate to service's API/keys page
2. Use `driver.execute_script()` with `fetch()` to call service's internal API
3. Or scrape the page for displayed keys
4. Save to Bitwarden immediately

## Session Refresh

Google sessions expire after ~2 weeks of inactivity. To refresh:
- Navigate to `https://myaccount.google.com/` periodically
- If redirected to sign-in, user needs to re-authenticate once
- Can add a cron job to check session validity

## Pitfalls

- **Google blocks headless sign-in**: The initial login MUST happen via a real browser (desktop/phone). Once the profile has cookies, headless works fine.
- **Profile corruption**: If Chrome crashes during login, delete the profile and recreate: `rm -rf ~/.hermes/chrome-profiles/google-main`
- **Multiple Google accounts**: If user has multiple accounts, Google shows "Choose an account" screen. Handle with: `driver.find_element(By.XPATH, "//div[contains(text(), 'target@email.com')]").click()`
- **OAuth consent screen**: Some services require explicit consent even with Google session. This shows as a "Allow access" page — click "Allow" via automation.
- **2FA**: If Google account has 2FA, the initial login needs the 2FA code. After that, the session persists without 2FA for the session duration.
- **Webtop svc-chromium broken**: The s6 service `svc-chromium` may fail with "unable to read type". Use host-side undetected-chromedriver instead.
