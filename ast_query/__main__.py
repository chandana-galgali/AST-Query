"""Allow ``python -m ast_query``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
