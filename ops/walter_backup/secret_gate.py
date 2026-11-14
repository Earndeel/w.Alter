"""Fail-closed gate before a git history leaves the machine: every blob of every ref is checked against the
vault's value fingerprints (Walter Secrets, value-free index) and against common credential shapes.
Output: JSON {repo: [{path, kind}]} — paths only, never a value. Exit 1 when anything is found."""
import json, re, subprocess, sys

# Token shapes a publisher may replace by a marker; a private key block is never "cleaned": it only refuses.
TOKEN_SHAPES = (r'sk-ant-api\d\d-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,}|sk-or-v1-[a-f0-9]{40,}|ghp_[A-Za-z0-9]{30,}'
                r'|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}'
                r'|AIza[0-9A-Za-z_-]{35}|\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b|ya29\.[A-Za-z0-9_-]{20,}|[rs]k_live_[A-Za-z0-9]{20,}')
PATTERNS = re.compile('(' + TOKEN_SHAPES + '|-----BEGIN [A-Z ]*PRIVATE KEY-----)')
MAX_BLOB = 3_000_000


def scrubber():
    root = subprocess.run(['walter', 'path', 'secrets'], capture_output=True, text=True).stdout.strip()
    if not root:   # the module is found through its interface only, never a guessed path (fail closed)
        raise SystemExit('walter path secrets gave nothing: refusing to clear a history')
    sys.path.insert(0, root)
    from walter_secrets import fingerprints
    if not fingerprints.status().get('ok'):
        raise SystemExit('vault fingerprint index unavailable: refusing to clear a history')
    return fingerprints.scrub


def scan(repo, scrub):
    lines = subprocess.run(['git', '-C', repo, 'rev-list', '--objects', '--all'], capture_output=True, text=True,
                           check=True).stdout.splitlines()
    paths = {}
    for l in lines:
        sha, _, p = l.partition(' ')
        if p:
            paths.setdefault(sha, p)
    batch = subprocess.Popen(['git', '-C', repo, 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    hits = []
    for sha, p in paths.items():
        batch.stdin.write((sha + '\n').encode()); batch.stdin.flush()
        header = batch.stdout.readline().split()
        kind, size = header[1].decode(), int(header[2])
        data = batch.stdout.read(size); batch.stdout.read(1)
        if kind != 'blob':
            continue
        if size > 50_000_000:
            hits.append({'path': p, 'kind': 'large file'}); continue
        if size > MAX_BLOB:
            continue
        text = data.decode('utf-8', 'ignore')
        if scrub(text) != text:
            hits.append({'path': p, 'kind': 'vault value'})
        if PATTERNS.search(text):
            hits.append({'path': p, 'kind': 'credential shape'})
    batch.stdin.close(); batch.wait()
    return hits


def main(argv):
    scrub = scrubber()
    out = {repo: scan(repo, scrub) for repo in argv}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if any(out.values()) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
