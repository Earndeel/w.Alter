"""Compatibility import for Walter Secrets; implementation belongs to /opt/walter-secrets."""
import importlib
import runpy
import sys
sys.path.insert(0, "/opt/walter-secrets")
if __name__ == "__main__":
    runpy.run_module("walter_secrets.vault_react", run_name="__main__")
else:
    sys.modules[__name__] = importlib.import_module("walter_secrets.vault_react")
