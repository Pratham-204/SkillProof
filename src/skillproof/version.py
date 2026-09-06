from pathlib import Path

# Written by CI's deploy job into the source tree it uploads to Railway, so
# the Dockerfile's existing `COPY src/ ./src/` bakes it into the image. It is
# deliberately absent in local dev, in tests, and in the Docker smoke test —
# "unknown" is the honest answer there, not a fabricated SHA.
_BUILD_SHA_FILE = Path(__file__).resolve().parent / "_build_sha.txt"


def deployed_sha() -> str:
    """The git commit this running container was built from, or "unknown".

    Exists so a deploy can be *verified* rather than assumed: `railway up`
    returns as soon as its upload is accepted, so a green deploy step proves
    nothing about what production is actually serving. Comparing this against
    the commit CI just pushed is what catches a Railway build that failed or
    was never rolled out, which otherwise leaves the previous container up
    with every check still green.
    """
    try:
        return _BUILD_SHA_FILE.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"
