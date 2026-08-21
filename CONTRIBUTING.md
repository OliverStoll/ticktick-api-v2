# Contributing

Contributions are welcome, especially for endpoints this library doesn't cover yet.

## Setup

```bash
git clone https://github.com/OliverStoll/ticktick-api-v2.git
cd ticktick-api-v2
pip install poetry
poetry install
```

## Running tests and lint

```bash
poetry run pytest tests/ -v
poetry run ruff check .
poetry run mypy ticktick_v2
```

CI runs the same checks on every push and pull request, against Python 3.11, 3.12, and 3.13.

## Finding new endpoints

This library talks to TickTick's internal `api/v2`, the same one the web app uses. The most reliable way to find or verify an endpoint is:

1. Open [ticktick.com](https://ticktick.com) in a browser with dev tools open, on the Network tab.
2. Trigger the feature you want to support (e.g. adding a subtask, setting a reminder).
3. Note the request URL, method, and JSON body. Redact your session cookies before sharing this anywhere.
4. Add a pydantic model for the response shape and a method on the relevant handler class, following the existing pattern in `tasks.py`/`habits.py`/`focus.py`/`events.py`.

## Style

- `ruff` for linting (`pyproject.toml` has the rule selection), line length 120.
- Type hints throughout; `mypy` is run in CI but isn't a hard gate yet since some of the older code predates full typing. New code should be typed.
- Tests for anything that doesn't require a live TickTick session (pure functions, pydantic model behavior). Auth-requiring code is hard to test in CI and isn't currently covered.
