"""Engine contracts (lot E0, 2026-11-09): the schemas are valid JSON Schema 2020-12, accept the reference examples,
refuse the unsafe ones (unstable session id, missing idempotency key, removed terminal toolset, unlimited depth,
an approval with no answerer, message text on the bus, a strategy without tests). No engine runs here."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from walter_platform import paths

HERE = Path(__file__).resolve().parent
CONTRACTS = HERE.parent / "contracts"
EXAMPLES = json.loads((HERE / "fixtures" / "contract-examples.json").read_text())


def _registry():
    resources = []
    for f in sorted(CONTRACTS.glob("*.json")):
        doc = json.loads(f.read_text())
        resources.append((doc["$id"], Resource.from_contents(doc)))
    plan = paths.module_path("context", "contracts", "schemas", "context-plan.v2.json")  # Context owns ContextPlan
    doc = json.loads(Path(plan).read_text())
    resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def _validator(name):
    schema = json.loads((CONTRACTS / name).read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=_registry())


def test_every_schema_is_declared_and_has_examples():
    names = {f.name for f in CONTRACTS.glob("*.json")}
    assert names == set(EXAMPLES["valid"]) == set(EXAMPLES["invalid"])
    for name in names:
        doc = json.loads((CONTRACTS / name).read_text())
        assert doc["$id"].endswith("/core/engine/" + name) and ("DRAFT" in doc["description"] or "IMPLEMENTED" in doc["description"])


@pytest.mark.parametrize("name", sorted(EXAMPLES["valid"]))
def test_reference_examples_are_accepted(name):
    v = _validator(name)
    for example in EXAMPLES["valid"][name]:
        errors = list(v.iter_errors(example))
        assert not errors, (example, [e.message for e in errors])


@pytest.mark.parametrize("name", sorted(EXAMPLES["invalid"]))
def test_unsafe_examples_are_refused(name):
    v = _validator(name)
    for example in EXAMPLES["invalid"][name]:
        assert list(v.iter_errors(example)), example
