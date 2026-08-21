# 📦 TickTick-Unofficial-Api

TickTick-Unofficial-Api is a Python wrapper for the unofficial TickTick API (v2).
It provides full read and write access to task, focus, habit, and calendar event data.
Authentication is handled via cookies retrieved either through Selenium or manually extracted browser sessions.

## ✨ Features

- Retrieve, create, update, and complete TickTick tasks
- Retrieve TickTick calendar events
- Retrieve and add TickTick habit entries
- Retrieve TickTick focus time data, and add historic focus records
- Retrieve the currently active (in progress) focus session

## 🗂️ Project Structure

```
src/  
└── ticktick_v2/  
    ├── utils/                 utility functions  
    ├── web/                   web-related functionality (e.g., Selenium login)  
    ├── cookies_login.py       handles cookie retrieval via Selenium  
    ├── events.py              calendar event access  
    ├── focus.py               focus session access and creation  
    ├── habits.py              habit access and writing  
    └── tasks.py               task access, creation, and updates
```

## 📥 Installation

To use the package, add [authentication](#-authentication) and install via:  
`pip install ticktick-py-v2`


## 🚀 Usage

You can use the module by importing `ticktick_v2`:
```
from ticktick_v2.habits import TicktickHabitHandler, TickTickHabitEntry 
from ticktick_v2.focus import TicktickFocusHandler, TickTickFocusTime
from ticktick_v2.tasks import TicktickTaskHandler, TickTickTask
from ticktick_v2.events import TicktickEventHandler, TicktickEvent
```

All return values use pydantic BaseModel for data validation. 
To use data as dict, simply convert via `.dict()`

### 🔐 Authentication

To access your TickTick data, you must authenticate using one of two methods:

#### Method 1: Environment Variables + Selenium

Set the following environment variables:  
`TICKTICK_USERNAME="your_email@example.com"`  
`TICKTICK_PASSWORD="your_password"`

The package will use a headless Selenium session to retrieve the necessary cookies for API access.

#### Method 2: Pre-saved Cookies

Create a file named `.ticktick-cookies` in your working directory. 
This file should contain cookies exported from a logged-in TickTick browser session (e.g., using browser developer tools).


## 🤝 Contributing

Contributions are welcome. Please open issues or pull requests for new features, improvements, or bug fixes.

## 🪪 License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
