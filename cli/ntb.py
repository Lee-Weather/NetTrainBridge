#!/usr/bin/env python3
"""向后兼容：请使用 ``ntb`` 或 ``python -m nettrainbridge_cli``。"""

from nettrainbridge_cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
