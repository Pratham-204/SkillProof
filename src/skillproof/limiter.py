import ipaddress
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

logger = logging.getLogger(__name__)


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
    header to spoof any IP it likes and mint a fresh rate-limit bucket on
    every request — only trust it behind a proxy known to set/overwrite it
    itself, which is why `get_remote_address` remains the fallback whenever
    the header is absent. This has been verified against Railway's own
    edge behavior (its docs describe overwriting, not appending to,
    X-Forwarded-For); it has NOT been re-verified against a live deployment
    from this codebase, and would silently stop holding if the app is ever
    reached through anything other than Railway's exact edge hop (e.g. an
    added internal proxy, a direct container port, or a future multi-region/
    CDN layer in front of Railway) — treat that as a standing follow-up
    before relying on this in a materially different deployment topology.

    Every endpoint that shares this key_func (including /verify's per-run
    start limit) is therefore bucketed per-IP, not per-candidate/user. This
    is a deliberate, considered tradeoff for this MVP's single-Railway-edge
    deployment: it is simple and closes the "one shared proxy hop for every
    client" bug above, at the cost that clients behind one shared NAT or
    corporate/office IP collectively share one budget. A per-candidate (or
    per-authenticated-user) secondary limit would remove that cost but needs
    its own key_func wired up at each call site, not just here.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        candidate = forwarded_for.split(",")[0].strip()
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            # Malformed/non-IP first hop: don't let garbage (or a
            # deliberately-crafted junk value) become a rate-limit bucket
            # key. Fall through to the proxy-hop address instead.
            logger.warning(
                "get_client_ip: ignoring malformed X-Forwarded-For value %r", candidate
            )
        else:
            return candidate
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip)
