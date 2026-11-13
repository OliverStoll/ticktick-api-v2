# 📦 ticktick-py-v2

[![CI](https://github.com/OliverStoll/ticktick-api-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/OliverStoll/ticktick-api-v2/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ticktick-py-v2)](https://pypi.org/project/ticktick-py-v2/)
[![Python](https://img.shields.io/pypi/pyversions/ticktick-py-v2)](https://pypi.org/project/ticktick-py-v2/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

A Python wrapper for TickTick's unofficial `api/v2` endpoint, the same one the web app and desktop clients use. It gives you **read and write** access to tasks, habits, focus/pomodoro sessions, and calendar events, without registering an OAuth app or waiting on TickTick's official API for features it doesn't expose.

The API is plain functions, not stateful client classes: call `create_task(...)`, `post_checkin(...)`, `add_focus_record(...)` directly, passing your auth headers along (or letting each call fetch them for you). No handler object to construct first.

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

Every function below takes an optional `headers` argument. Fetch it once with `get_authenticated_ticktick_headers()` and pass it to every call to avoid re-authenticating each time, or leave it out and it's fetched fresh (cheap once your login is cached on disk).

```python
from ticktick_v2.cookies_login import get_authenticated_ticktick_headers

auth = get_authenticated_ticktick_headers()
```

### Tasks

```python
from ticktick_v2.tasks import (
    create_task, complete_task, get_active_tasks, get_all_projects,
    add_project_properties_to_tasks,
)

# read
active = get_active_tasks(headers=auth)
projects = get_all_projects(headers=auth)
active = add_project_properties_to_tasks(active, projects)  # fills in project_name etc.

# write
task = create_task(title="Buy milk", project_id=next(iter(projects)), headers=auth)
complete_task(task.id, task.project_id, headers=auth)
```

### Habits

```python
from ticktick_v2.habits import post_checkin, get_all_checkins

# read
checkins = get_all_checkins(after_stamp=20260101, headers=auth)

# write, e.g. to backfill a habit from another data source
post_checkin("Meditate", date_stamp=20260115, status=2, headers=auth)  # 2 = completed
```

### Focus / Pomodoro sessions

```python
from datetime import datetime
from ticktick_v2.focus import get_all_focus_times, get_active_focus_time, add_focus_record

# read
recent = get_all_focus_times(days_offset=30, headers=auth)
currently_running_minutes = get_active_focus_time(headers=auth)

# write, e.g. to backfill historic focus time from another app
add_focus_record(
    start=datetime(2026, 1, 15, 9, 0),
    end=datetime(2026, 1, 15, 10, 30),
    headers=auth,
)
```

### Calendar events

```python
from ticktick_v2.events import get_all_events

events = get_all_events(headers=auth)
```

All return values are `pydantic` `BaseModel`s. Convert to a plain dict with `.model_dump()`, or `.model_dump(by_alias=True)` for TickTick's native camelCase field names.

## 🤖 MCP server

The same client, exposed as an MCP server so Claude Desktop, Claude Code, Cursor,
VS Code and other MCP clients can read and write your TickTick data directly.

```
pip install "ticktick-py-v2[mcp]"
```

```bash
claude mcp add ticktick -- ticktick-mcp

# credentials for the headless login, if you want it to log itself in
claude mcp add ticktick --env TICKTICK_EMAIL=you@example.com --env TICKTICK_PASSWORD=... \
  --env TICKTICK_AUTO_LOGIN=true -- ticktick-mcp
```

For clients configured through JSON:

```json
{
  "mcpServers": {
    "ticktick": {
      "command": "ticktick-mcp",
      "env": {
        "TICKTICK_COOKIES_FILE": "/home/you/.ticktick-cookies.json",
        "TICKTICK_TOOL_PROFILE": "essential"
      }
    }
  }
}
```

VS Code uses the same entry under a `servers` key with `"type": "stdio"`. Zed
uses `context_servers`. `python -m ticktick_v2.mcp` does the same as
`ticktick-mcp` if the console script is not on your `PATH`.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `TICKTICK_EMAIL`, `TICKTICK_PASSWORD` | unset | Login credentials; only read from the environment |
| `TICKTICK_COOKIES_FILE` | unset | Path to exported cookies, used instead of logging in |
| `TICKTICK_COOKIE_STORE` | `$XDG_STATE_HOME/ticktick-mcp` | Where the session is cached after a login |
| `TICKTICK_AUTO_LOGIN` | `false` | Set exactly `true` to allow the headless Selenium login |
| `TICKTICK_HEADLESS` | `true` | Set `false` to watch the login browser |
| `TICKTICK_TIMEZONE` | system local | Timezone for reading and writing dates |
| `TICKTICK_TOOL_PROFILE` | `full` | `full` or `essential`; changes the advertised tool set |
| `TICKTICK_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `TICKTICK_MCP_HOST`, `TICKTICK_MCP_PORT` | `127.0.0.1`, `8765` | Bind address for the HTTP transport |
| `TICKTICK_MCP_TOKEN` | unset | Bearer token required by the HTTP transport |
| `TICKTICK_MCP_USERNAME`, `TICKTICK_MCP_PASSWORD` | unset | Basic-auth pair for the HTTP transport |

The server never logs in on its own unless `TICKTICK_AUTO_LOGIN=true`: Selenium
is a heavy start for a process an editor launches, so the default is to use the
cookies file if it is valid and otherwise report what is missing. `get_login_status`
shows which of the two applies, including the cookie file's age and, with
`check_network=true`, whether TickTick still accepts it.

The `essential` profile keeps the reads plus the additive writes (`create_task`,
`complete_task`, `check_in_habit`) and drops `update_task`, `set_task_status`,
`delete_task` and `add_focus_record`. Like any tool profile it is a discovery
choice, not a security boundary: the tools it does advertise can still write.

The HTTP transport refuses to bind off loopback unless a token or an
username/password pair is configured.

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
