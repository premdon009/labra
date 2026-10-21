"""The container health check: `python -m labra.probe /readyz` exits 0 when the app answers.

No argument holds a space, as Podman 5 splits a Compose health check's arguments at spaces.
Only the standard library, so the check starts quickly.
"""

import sys
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8000"


def probe(path: str, base: str = URL, timeout: float = 4) -> str | None:
    """None when `path` answers 200, otherwise why not."""
    try:
        with urllib.request.urlopen(base + path, timeout=timeout) as response:  # noqa: S310 - http only
            return None if response.status == 200 else f"{path} answered {response.status}"
    except urllib.error.HTTPError as e:
        with e:
            return f"{path} answered {e.code}"
    except OSError as e:
        return f"{path} did not answer: {e}"


def main(argv: list[str]) -> int:
    problem = probe(argv[0] if argv else "/healthz")
    if problem:
        sys.stderr.write(problem + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
