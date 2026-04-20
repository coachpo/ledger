from __future__ import annotations

import json
import sys


def main() -> None:
    json.dump(
        {
            "name": "ledger-stock-analysis-reference-server",
            "status": "ready",
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
