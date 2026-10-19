"""Enable ``python -m nova ...`` as an alias for the ``nova`` console script."""

from __future__ import annotations

from nova.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
