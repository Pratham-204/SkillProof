from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def get_client_ip(request: Request) -> str:
    """Resolves the real client IP for slowapi's rate-limit bucket key.

    The stock `get_remote_address` reads only `request.client.host` — behind
    Railway's edge proxy (this app's only documented deployment target, per
    ADR-0009/0010) that is always the proxy's own internal hop address, not
    the visitor's, since Railway terminates TLS and forwards every request
    over its internal network. That collapses every distinct client into one
    shared rate-limit bucket regardless of who actually sent the request.

    Railway's edge sets (and overwrites, rather than blindly appends to)
    X-Forwarded-For with the real client IP as its first value, so trusting
    that first hop is safe there. This is NOT a safe assumption for an
    arbitrary unproxied deployment, where a direct client could forge this
    header to spoof any IP it likes — only trust it behind a proxy known to
    set/overwrite it itself, which is why `get_remote_address` remains the
    fallback whenever the header is absent.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip)
