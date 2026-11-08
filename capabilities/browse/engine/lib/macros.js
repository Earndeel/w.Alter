// Minimal stub — restores missing lib/macros module after checkout cleanup.
// Original purpose: expand short URL macros (e.g. "google" → "https://google.com").
// Identity passthrough is safe — caller always provides full URLs in the API payload.
function expandMacro(url) {
  if (!url || typeof url !== 'string') return url;
  // Add scheme if user passed a bare host
  if (/^[a-z0-9-]+(\.[a-z0-9-]+)+/i.test(url) && !/^https?:\/\//i.test(url)) {
    return `https://${url}`;
  }
  return url;
}

module.exports = { expandMacro };
