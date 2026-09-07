"""Unit tests for skillproof.limiter's rate-limit key function, isolated from
the full ASGI app (see test_api_flow.py for the end-to-end 429 behavior)."""

from starlette.requests import Request

from skillproof.limiter import get_client_ip


def _request(headers: dict[str, str], client_host: str | None) -> Request:
    scope = {
        "type": "http",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


def test_get_client_ip_uses_first_hop_of_x_forwarded_for():
    """Railway's edge sets X-Forwarded-For with the real visitor IP as the
    first value; request.client.host at this point is only the proxy's own
    internal hop, which the key function must not key on instead."""
    request = _request({"x-forwarded-for": "203.0.113.5, 10.0.0.1"}, client_host="10.0.0.1")

    assert get_client_ip(request) == "203.0.113.5"


def test_get_client_ip_falls_back_to_remote_address_without_the_header():
    request = _request({}, client_host="198.51.100.7")

    assert get_client_ip(request) == "198.51.100.7"


def test_get_client_ip_distinguishes_two_clients_sharing_one_proxy_hop():
    """Regression: slowapi's stock get_remote_address reads only
    request.client.host, which — behind Railway's edge proxy — is the same
    proxy address for every request, collapsing every real client into one
    shared rate-limit bucket regardless of who actually sent the request."""
    candidate_a = _request({"x-forwarded-for": "203.0.113.5"}, client_host="10.0.0.1")
    candidate_b = _request({"x-forwarded-for": "198.51.100.9"}, client_host="10.0.0.1")

    assert get_client_ip(candidate_a) != get_client_ip(candidate_b)
