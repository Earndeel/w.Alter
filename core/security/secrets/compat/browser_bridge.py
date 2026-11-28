"""Legacy import for the Hermes-specific browser port."""
import importlib
import sys
sys.path.insert(0, "/walter/core/security/secrets")
sys.modules[__name__] = importlib.import_module("walter_secrets.ports.hermes.browser_bridge")
