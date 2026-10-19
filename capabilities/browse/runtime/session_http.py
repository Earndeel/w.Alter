"""Scoped HTTP read port for managed authenticated sessions. No secret output."""
import http.cookiejar
import json
import os
import stat
import time
import urllib.parse
import urllib.request
from browse_session import SessionManager, SessionError


class _SameOrigin(urllib.request.HTTPRedirectHandler):
    def __init__(self, origin):
        self.origin = origin

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if _origin(newurl) != self.origin:
            raise SessionError('authenticated redirect leaves its authorized origin')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _origin(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password:
        raise SessionError('invalid session URL')
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80)


def session_opener(session, url):
    if session.network != 'local':
        raise SessionError('authenticated HTTP has no configured session proxy adapter')
    origin = _origin(url)
    path = SessionManager().storage_state_path(session)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise SessionError('managed session storage must be private')
            text = stream.read(2_097_153)
            if len(text) > 2_097_152:
                raise SessionError('managed session storage too large')
            state = json.loads(text)
    except (OSError, ValueError, TypeError):
        raise SessionError('managed session storage unavailable') from None
    jar = http.cookiejar.CookieJar(http.cookiejar.DefaultCookiePolicy(
        strict_ns_domain=http.cookiejar.DefaultCookiePolicy.DomainStrictNonDomain))
    from browse_session import cookies_for_domain
    cookies = cookies_for_domain(state.get('cookies', []), origin[1])
    for item in cookies:
        domain = str(item.get('domain') or '')
        expiry = item.get('expires', -1)
        expiry = int(expiry) if isinstance(expiry, (int, float)) and expiry > 0 else None
        if expiry is not None and expiry <= time.time():
            continue
        name, value = str(item.get('name', '')), str(item.get('value', ''))
        if not name or any(c in name + value for c in '\r\n'):
            raise SessionError('invalid managed cookie')
        jar.set_cookie(http.cookiejar.Cookie(0, name, value, None, False,
            domain, domain.startswith('.'), domain.startswith('.'), str(item.get('path') or '/'), True,
            bool(item.get('secure')), expiry, expiry is None, None, None, {}, False))
    if not len(jar):
        raise SessionError('no managed credential applies to this origin')
    # Only the server-side jar handles values; redirect scope and RFC cookie
    # domain/path/expiry/secure checks remain enforced on each request.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(jar), _SameOrigin(origin))
