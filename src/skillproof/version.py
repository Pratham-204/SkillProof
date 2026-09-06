import os
from pathlib import Path

# Overwritten by CI's deploy job in the source tree it uploads to Railway, so
# the Dockerfile's existing `COPY src/ ./src/` bakes it into the image. It is
# committed holding "unknown" rather than gitignored: `railway up` honors
# .gitignore when packaging its upload, so an ignored stamp file is stripped
# out of the very build it exists to identify (that is exactly how the first
# version of this failed).
_BUILD_SHA_FILE = Path(__file__).resolve().parent / "_build_sha.txt"

_UNKNOWN = "unknown"


def deployed_sha() -> str:
    """The git commit this running container was built from, or "unknown".

    Exists so a deploy can be *verified* rather than assumed: `railway up`
    returns as soon as its upload is accepted, so a green deploy step proves
    nothing about what production is actually serving.

    Two sources, because this project has two live deploy paths: Railway's own
    GitHub-connected builds (which inject RAILWAY_GIT_COMMIT_SHA) and CI's
    `railway up` upload (which carries the stamp file). Either one identifying
    the running commit is enough; "unknown" means neither did, which in
    production means something deployed a build nobody stamped.
    """
    railway_sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "").strip()
    if railway_sha:
        return railway_sha
    try:
        return _BUILD_SHA_FILE.read_text(encoding="utf-8").strip() or _UNKNOWN
    except OSError:
        return _UNKNOWN
