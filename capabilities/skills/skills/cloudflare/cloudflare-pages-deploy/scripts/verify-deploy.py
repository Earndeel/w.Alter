#!/usr/bin/env python3
"""Verify a Cloudflare Pages deployment has fresh content.
Run after deploy to confirm CSS/JS assets are served with new content.
Usage: python3 scripts/verify-deploy.py https://your-site.pages.dev
"""
import sys, urllib.request

def check_fresh(url):
    errors = []
    for path, marker in [
        ("/assets/style.css", b"--accent"),
        ("/assets/app.js", b"function"),
    ]:
        try:
            req = urllib.request.Request(url + path, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read()
                if marker not in data:
                    errors.append(f"  {path}: marker '{marker.decode()}' NOT FOUND")
                else:
                    print(f"  OK {path} ({len(data)} bytes)")
        except Exception as e:
            errors.append(f"  {path}: ERROR {e}")
    
    if errors:
        print("FAILURES:")
        for e in errors:
            print(e)
        sys.exit(1)
    print("All checks passed.")

if __name__ == "__main__":
    check_fresh(sys.argv[1] if len(sys.argv) > 1 else "https://scena.walter-ai.cloud")
