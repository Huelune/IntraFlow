from __future__ import annotations


def main() -> int:
    # PySide6 application bootstrap will be implemented after DB/sync foundation.
    print("IntraFlow DB foundation is ready. Run `alembic upgrade head` and `pytest`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
