"""Usage: python -m jevcheck FILE"""

import sys

from jevcheck.check import check


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    report = check(sys.argv[1])
    print(report.model_dump_json(indent=2))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
