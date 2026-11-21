# Camoufox-max Server Stability Patches

## Problem
Long-running browser sessions (AWS console, multi-step auth flows) crash silently. The server reports success but the browser is dead. All subsequent operations fail with "Target page, context or browser has been closed".

## Root Cause
Browser process crashes or is killed externally. Camoufox server doesn't detect the crash and continues trying to use the dead context.

## Solution: Health Check + Auto-Restart

### 1. Add Health Check Function
```javascript
async function isBrowserAlive() {
  try {
    if (!browserContext || !browserContext._browser) return false;
    const pages = browserContext.pages();
    if (!pages || pages.length === 0) return false;
    await pages[0].evaluate('1+1');
    return true;
  } catch (e) {
    return false;
  }
}
```

### 2. Add Auto-Restart Wrapper
```javascript
async function ensureBrowserHealthy() {
  if (!(await isBrowserAlive())) {
    console.log('Browser unhealthy, restarting...');
    await startBrowser();
    return true; // restarted
  }
  return false; // was healthy
}
```

### 3. Add Health Endpoint
```javascript
app.get('/health', async (req, res) => {
  const alive = await isBrowserAlive();
  res.json({ ok: alive, browser: alive ? 'running' : 'dead' });
});
```

### 4. Add Restart Endpoint
```javascript
app.post('/restart', async (req, res) => {
  try {
    await startBrowser();
    res.json({ ok: true, message: 'Browser restarted' });
  } catch (e) {
    res.json({ ok: false, error: e.message });
  }
});
```

### 5. Wrap All Browser Operations
Every endpoint that interacts with the browser should call `ensureBrowserHealthy()` first:
```javascript
app.post('/tab/evaluate', async (req, res) => {
  await ensureBrowserHealthy();
  // ... existing logic
});

app.post('/tab/navigate', async (req, res) => {
  await ensureBrowserHealthy();
  // ... existing logic
});

app.get('/tab/screenshot', async (req, res) => {
  await ensureBrowserHealthy();
  // ... existing logic
});

app.get('/tab/snapshot', async (req, res) => {
  await ensureBrowserHealthy();
  // ... existing logic
});
```

## Verification
```bash
# Check health
curl http://localhost:9378/health

# Force restart
curl -X POST http://localhost:9378/restart

# Test with a long-running session
# Navigate to AWS console, wait 5+ minutes, then try to interact
# Should auto-recover if browser crashed
```

## Notes
- The health check uses `evaluate('1+1')` as a lightweight probe
- Auto-restart preserves the server process but creates a new browser context
- Cookies injected before the crash are lost — re-inject after restart
- This pattern is critical for AWS console automation where sessions are long-lived
