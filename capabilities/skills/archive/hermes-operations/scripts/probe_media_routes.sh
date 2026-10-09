#!/usr/bin/env bash
# Probe a Hermes web server's media/byte-delivery routes and their auth guardrails.
#
# Usage: probe_media_routes.sh BASE_URL SESSION_TOKEN FILE_PATH [FILE_PATH_2]
#   BASE_URL      e.g. http://127.0.0.1:8787
#   SESSION_TOKEN value of X-Hermes-Session-Token
#   FILE_PATH     absolute path of a media file the server can read (second is optional)
#
# Verifies, in order:
#   A. byte delivery via URL token   (what <video src> / <a download> use)
#   B. Range/seek with no header     (playback)
#   C. guardrails still refuse       (listings, text reads, writes)
#   D. no credential is still 401
set -u
BASE=${1:?BASE_URL}; TOKEN=${2:?SESSION_TOKEN}; P1=${3:?FILE_PATH}; P2=${4:-}
enc() { python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$1"; }
E1=$(enc "$P1"); E2=$([ -n "$P2" ] && enc "$P2" || echo "$E1")
H="X-Hermes-Session-Token: $TOKEN"
show() { printf '%-42s %s\n' "$1" "$(curl -s -o /dev/null -w "$2" ${3:-} -H "$H" "$4")"; }
DIR=$(enc "$(dirname "$P1")")

printf '== A. byte delivery via ?token= ==\n'
for r in files/stream files/download; do
  show "GET /api/$r  file1" '%{http_code} ct=%{content_type}' '' "$BASE/api/$r?path=$E1&token=$TOKEN"
  show "GET /api/$r  file2" '%{http_code} ct=%{content_type}' '' "$BASE/api/$r?path=$E2&token=$TOKEN"
done
for r in fs/download fs/read-data-url; do
  show "GET /api/$r" '%{http_code} ct=%{content_type}' '' "$BASE/api/$r?path=$E1&token=$TOKEN"
done

printf '\n== B. Range / seek with no header ==\n'
show 'Range 0-999 on files/stream' '%{http_code} bytes=%{size_download}' '-H "Range: bytes=0-999"' "$BASE/api/files/stream?path=$E1&token=$TOKEN"
show 'deep seek on files/download' '%{http_code} bytes=%{size_download}' '-H "Range: bytes=5000000-5000999"' "$BASE/api/files/download?path=$E1&token=$TOKEN"
printf '   expect 206 for both (200 with full body = not seekable)\n'

printf '\n== C. guardrails MUST refuse ?token= ==\n'
show 'GET /api/files     (listing)' '%{http_code}' '' "$BASE/api/files?path=$DIR&token=$TOKEN"
show 'GET /api/fs/list  (listing)' '%{http_code}' '' "$BASE/api/fs/list?path=$DIR&token=$TOKEN"
show 'GET /api/files/read' '%{http_code}' '' "$BASE/api/files/read?path=$E1&token=$TOKEN"
show 'POST /api/files/upload' '%{http_code}' '-X POST' "$BASE/api/files/upload?path=$E1&token=$TOKEN"
printf '   expect 401 for all four\n'

printf '\n== D. no credential MUST be 401 ==\n'
for r in files/stream files/download fs/download fs/read-data-url; do
  show "GET /api/$r (no token)" '%{http_code}' '' "$BASE/api/$r?path=$E1"
done
printf '   expect 401 for all four\n'
