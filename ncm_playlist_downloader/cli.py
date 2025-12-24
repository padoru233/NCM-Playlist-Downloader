"""Small CLI wrapper that runs the top-level `script` module.

We avoid modifying the original `script.py` by executing it as a module.
This lets us provide a console_scripts entry point that runs the existing script.
"""
from __future__ import annotations

import runpy
import sys


def main(argv: list | None = None) -> int:
    """Entry point for console_scripts.

    This will execute the installed `script` module as __main__, so behavior is
    equivalent to `python -m script` or `python script.py`.
    """
    if argv is not None:
        # adjust sys.argv for the executed module
        sys.argv[:] = [sys.argv[0]] + list(argv)
    try:
        runpy.run_module('script', run_name='__main__')
        return 0
    except SystemExit as e:
        # propagate exit codes
        code = e.code if isinstance(e.code, int) else 0
        return int(code)
    except Exception as e:
        print(f"ncm-playlist-downloader failed: {e}", file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
