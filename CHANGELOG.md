# Changelog

## 0.25.0

- **Tasks**: add `create_task`, `update_task`, `complete_task`, `change_task_status`, `get_active_tasks`, `get_abandoned_tasks`, `mark_recurring_complete`, `get_all_projects`
- **Focus**: add `add_focus_record` to write historic focus/pomodoro sessions, `get_active_focus_data`/`get_active_focus_time` to read the currently running session
- **Events**: new `events.py` module with `TicktickEventHandler` for calendar event access
- **Habits**: updated authentication, now supports `headless`/`undetected` Selenium options and a custom cookies path
- Fixed: `undetected` Selenium mode was broken by an undefined-name bug (`uc` shadowed by a later local import); also fixed the resulting Python 3.12+/3.13 compatibility issue (`undetected-chromedriver` pulls in `distutils`, removed from the stdlib)
- Fixed: `TickTickTask.repeat_days` raised `AttributeError` for any unrecognized repeat frequency or malformed interval, since it called `self.log` on the pydantic model, which never had a logger
- Fixed: an invalid `callable` type hint (should be `typing.Callable`) in `CookiesManager.__init__`
- Removed leaked GCP-specific logging setup from the shared logger helper (it isn't relevant to this library and wasn't a declared dependency)
- Added a pytest suite and CI (tests on Python 3.11-3.13, plus lint)
- Added a `poetry.lock` for reproducible installs
- Added a PyPI trusted-publishing workflow (triggered on GitHub release)
- Bumped `pytest` to 9.1.1 (fixes a moderate advisory in `pytest < 9.0.3`)

## 0.24.1

- Project restructuring, description update
