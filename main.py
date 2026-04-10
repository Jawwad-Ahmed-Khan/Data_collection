"""
ClimaSync.ai — Data Collection Service entry point.

Run with:
    uv run python main.py
or:
    uv run uvicorn app.main:app --reload
"""

from app.main import main

if __name__ == "__main__":
    main()
