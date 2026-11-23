"""Backwards-compatible entry point: ``python -m ast_query.main``.

Both the original ``<file> "<query>"`` order and the new
``"<query>" [paths...]`` order are accepted.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
