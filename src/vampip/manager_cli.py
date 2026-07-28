from __future__ import annotations

import sys

from vampip.cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    return cli_main(["manager", "serve", *arguments])


if __name__ == "__main__":
    raise SystemExit(main())
