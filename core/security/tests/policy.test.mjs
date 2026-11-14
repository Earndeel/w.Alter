// The JS side of the one execution policy against the shared vectors (the Python side runs the same file).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { decide, load, POLICY } from '../policy.mjs';

const ROOT = '/user/Test';
const vectors = JSON.parse(readFileSync(new URL('./vectors.json', import.meta.url), 'utf8'));
const p = load(POLICY, ROOT);

for (const c of vectors) {
  test(c.why, () => {
    const req = JSON.parse(JSON.stringify(c.req).replaceAll('@instance', ROOT));
    const out = decide(p, req);
    assert.equal(out.decision, c.decision, JSON.stringify(out));
    if (c.rule) assert.equal(out.rule, c.rule);
  });
}
