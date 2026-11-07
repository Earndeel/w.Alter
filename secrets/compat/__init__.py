"""Hermes adapter. Walter Secrets is a shared module, independent of this runtime."""
import sys
sys.path.insert(0, "/opt/walter-secrets")
from walter_secrets.ports.hermes import register
