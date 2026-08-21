# 📦 ticktick-py-v2

[![CI](https://github.com/OliverStoll/ticktick-api-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/OliverStoll/ticktick-api-v2/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ticktick-py-v2)](https://pypi.org/project/ticktick-py-v2/)
[![Python](https://img.shields.io/pypi/pyversions/ticktick-py-v2)](https://pypi.org/project/ticktick-py-v2/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

A Python wrapper for TickTick's unofficial `api/v2` endpoint, the same one the web app and desktop clients use. It gives you **read and write** access to tasks, habits, focus/pomodoro sessions, and calendar events, without registering an OAuth app or waiting on TickTick's official API for features it doesn't expose.

## Why this instead of the official API or `ticktick-py`?

TickTick's [official OAuth API](https://developer.ticktick.com/docs#/openapi) only covers tasks and projects, read-only for habits, and has no focus/pomodoro endpoints at all. This library talks to the same internal `api/v2` the apps use, so it additionally supports:

| | official API | ticktick-py-v2 |
|---|:---:|:---:|
| Read/write tasks | ✅ | ✅ |
| Read/write habit check-ins | ❌ | ✅ |
| Read focus/pomodoro sessions | ❌ | ✅ |
| **Write** (backfill) focus/pomodoro sessions | ❌ | ✅ |
| Read calendar events | ❌ | ✅ |
| No OAuth app registration | ❌ | ✅ |

The tradeoff: it's an unofficial, reverse-engineered API, so it can break if TickTick changes their internal endpoints. It authenticates via your normal login session (cookies), not OAuth.

## 📥 Installation

```bash
pip install ticktick-py-v2
```

## 🔐 Authentication

Set your TickTick credentials as environment variables and the library handles login for you via a headless Selenium session, caching the resulting cookies so subsequent runs don't need to log in again:

```bash
export TICKTICK_EMAIL="your_email@example.com"
export TICKTICK_PASSWORD="your_password"
```

Or manually export cookies from a logged-in browser session into a `.ticktick-cookies.json` file in your working directory.

## 🚀 Usage

### Tasks

```python
from ticktick_v2.tasks import TicktickTaskHandler

handler = TicktickTaskHandler()

# read
active = handler.get_active_tasks()
projects = handler.get_all_projects()

# write
task = handler.create_task(title="Buy milk", project_id=projects[0].id)
handler.complete_task(task.id, task.project_id)
```

### Habits

```python
from ticktick_v2.habits import TicktickHabitHandler

handler = TicktickHabitHandler()

# read
checkins = handler.get_all_checkins(after_stamp=20260101)

# write, e.g. to backfill a habit from another data source
handler.post_checkin("Meditate", date_stamp=20260115, status=2)  # 2 = completed
```

### Focus / Pomodoro sessions

```python
from datetime import datetime
from ticktick_v2.focus import TicktickFocusHandler

handler = TicktickFocusHandler()

# read
recent = handler.get_all_focus_times(days_offset=30)
currently_running_minutes = handler.get_active_focus_time()

# write, e.g. to backfill historic focus time from another app
handler.add_focus_record(
    start=datetime(2026, 1, 15, 9, 0),
    end=datetime(2026, 1, 15, 10, 30),
)
```

### Calendar events

```python
from ticktick_v2.events import TicktickEventHandler

handler = TicktickEventHandler()
events = handler.get_all_events()
```

All return values are `pydantic` `BaseModel`s. Convert to a plain dict with `.model_dump()`, or `.model_dump(by_alias=True)` for TickTick's native camelCase field names.

## 🗂️ Project structure

```
ticktick_v2/
├── utils/                 logging, config, timestamp helpers
├── web/                   HTTP request + Selenium login internals
├── cookies_login.py       cookie retrieval and caching
├── events.py              calendar event access
├── focus.py               focus/pomodoro session read and write
├── habits.py              habit check-in read and write
└── tasks.py               task and project read, create, and update
```

## ✅ Testing

```bash
pip install -e . pytest
pytest tests/ -v
```

## 🤝 Contributing

Issues and pull requests are welcome, especially for endpoints this library doesn't cover yet (recurring task edge cases, subtasks, reminders). If TickTick changes an endpoint and something here breaks, a bug report with the failing request/response is the fastest way to get it fixed.

## 🪪 License

Apache License 2.0. See [LICENSE](LICENSE).
