# 🚀 JXE HOSTING HUB


![JXE Hosting
BOT](https://capsule-render.vercel.app/api?type=waving&height=220&text=JXE%20HOSTING%20BOT&fontAlign=50&fontAlignY=38&desc=Telegram%20Powered%20Project%20Hosting%20Control%20Center&descAlignY=60&animation=twinkling&fontColor=ffffff&color=0:0f172a,50:2563eb,100:7c3aed)

![Typing
Animation](https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=24&pause=900&color=58A6FF&center=true&vCenter=true&width=800&lines=Deploy+Projects+from+Telegram+%E2%9A%A1;Manage+Files+%7C+Logs+%7C+ENV+%7C+Backups;Live+CPU+%2B+RAM+%2B+Uptime+Monitoring;Auto-Restart+%2B+Crash+Protection;Admin+Controls+%2B+Force+Join+%2B+Reports)

![JXE](https://img.shields.io/badge/JXE-HOSTING%20HUB-7c3aed?style=for-the-badge&logo=telegram&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)
![Status](https://img.shields.io/badge/Status-ONLINE-22c55e?style=for-the-badge)

**A powerful Telegram-based hosting hub for deploying, monitoring,
editing and controlling projects --- directly from Telegram.**
:::

------------------------------------------------------------------------

## ✨ What Is JXE Hosting Hub?

**JXE Hosting Hub** turns a Telegram bot into a lightweight
project-management and hosting control center.

Upload a project as a `.zip`, select its entry file, launch it, inspect
logs, manage files, configure `.env` variables, monitor resources,
restart crashed services, and create backups --- all through Telegram.

------------------------------------------------------------------------

## ⚡ Features

### 📦 Deployment

-   Upload `.zip` project archives
-   Automatic project directory creation
-   Entry-file discovery
-   Python / Node.js / Bash execution
-   Automatic free-port allocation
-   `PORT` environment support

### 🖥️ Project Control

-   Start / Stop
-   Restart
-   Live status
-   CPU usage
-   RAM usage
-   Uptime
-   Restart counter
-   Project dashboard

### 📁 Online File Manager

-   Browse files
-   View source
-   Edit files
-   Create files
-   Create folders
-   Replace files
-   Rename files
-   Download files
-   Remove files

### 🧰 Runtime Tools

-   Live logs
-   Full-log download
-   `.env` editor
-   Dependency installation helper
-   Full project backup
-   Auto-restart toggle
-   Crash detection

### 🛡️ Security

-   ZIP path traversal protection
-   Symlink ZIP entry blocking
-   Project-root path validation
-   Outside-project path protection
-   Restricted project environment

### 👑 Admin System

-   Admin-only control panel
-   User/project controls
-   Project limits
-   Force Join
-   Maintenance mode
-   Deployment enable/disable
-   Queue control
-   Report group
-   JSON storage backup
-   User suspension

------------------------------------------------------------------------

## 🎬 Animated Workflow

``` text
                 👤 TELEGRAM USER
                        │
                        ▼
                🚀 DEPLOY NEW
                        │
                        ▼
                   📦 UPLOAD ZIP
                        │
                        ▼
              🔐 VALIDATE + EXTRACT
                        │
                        ▼
                  🎯 SELECT ENTRY
                        │
                        ▼
                    🟢 START
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
      📊 MONITOR      ☷ LOGS       📁 FILES
          │             │             │
          └─────────────┼─────────────┘
                        ▼
                 ⚙️ CONTROL PANEL
                        │
                ┌───────┴───────┐
                ▼               ▼
            ♻️ AUTO          📦 BACKUP
            RESTART
```

------------------------------------------------------------------------

## 🔄 Project Lifecycle

![Lifecycle
Animation](https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=800&size=20&pause=600&color=22C55E&center=true&vCenter=true&width=900&lines=%5B01%5D+UPLOAD+%E2%86%92+%5B02%5D+EXTRACT+%E2%86%92+%5B03%5D+SCAN+%E2%86%92+%5B04%5D+RUN+%E2%86%92+%5B05%5D+MONITOR;Crash+%3F+%E2%86%92+Auto-Restart+%E2%86%92+Crash+Protection+%E2%86%92+Stable+Runtime)

The runtime monitor can detect crashed projects and request automatic
restarts when enabled. Repeated crashes can trigger crash protection and
pause automatic restarting.

------------------------------------------------------------------------

## 📊 Live Monitoring

``` text
╭──────────────────────────────────────────╮
│             🖥️ SERVER STATUS             │
├──────────────────────────────────────────┤
│ ☁️ Platform      : Cloud Compute         │
│ ⚡ CPU           : LIVE                  │
│ 💾 RAM           : LIVE                  │
│ 📦 Storage       : LIVE                  │
│ 🆓 Free Space    : LIVE                  │
│ 🟢 Service       : ONLINE                │
╰──────────────────────────────────────────╯
```

Project dashboards expose:

-   CPU usage
-   RAM usage
-   Uptime
-   Restart count
-   Port
-   Auto-restart state
-   Time remaining

------------------------------------------------------------------------

## 🎨 Telegram UI

  Action                                 Button Style
  -------------------------------------- --------------
  🚀 Deploy / Start / Install / Create   🟢 Success
  🧭 Navigation / Management / Info      🔵 Primary
  🗑 Delete / Stop / Remove / Clear       🔴 Danger

The UI uses consistent action-based styling rather than random button
colors.

------------------------------------------------------------------------

## 📁 Online File Manager

``` text
📁 PROJECT FILES

📄 main.py
   ✏️ Edit    🔁 Replace    📥 Download
   ✏️ Rename  🗑 Remove

➕ New File
➕ New Folder
```

Manage your project directly from Telegram without manually opening the
server filesystem.

------------------------------------------------------------------------

## 📝 Environment Variables

Configure project variables with:

``` env
KEY=VALUE
```

The `.env` panel supports:

-   View current variables
-   Add variables
-   Clear `.env`
-   Return to project control

------------------------------------------------------------------------

## 🔌 PORT Support

Web/server projects receive an automatically allocated free port:

``` env
PORT=<assigned-port>
```

Your application can read the `PORT` environment variable normally.

------------------------------------------------------------------------

## ⏳ Expiry & Queue

JXE Hosting Hub supports:

-   Online-time limits
-   Expiry tracking
-   Expiry grace period
-   Concurrent project limits
-   Start queue
-   Automatic stopping after expiry

``` text
PROJECT START REQUEST
          │
          ▼
   ┌───────────────┐
   │ SLOT AVAILABLE│
   └───────┬───────┘
       YES │     │ NO
           │     │
           ▼     ▼
        🟢 RUN  🟡 QUEUE
                 │
                 ▼
          ⏱️ WAIT FOR SLOT
                 │
                 ▼
              🟢 START
```

------------------------------------------------------------------------

## 👑 Admin Command Center

The administrator can manage:

-   👥 Users
-   📦 Project limits
-   📢 Force Join
-   🛠 Maintenance mode
-   🚀 Deployment availability
-   ♻️ Auto-restart defaults
-   ⏳ Queue settings
-   📡 Report group
-   📥 JSON backup
-   🚫 User suspension

Admin callbacks are protected by an admin-only permission check.

------------------------------------------------------------------------

## 📡 Report Group

When enabled, project events can be reported to a configured Telegram
group.

Reports can include:

-   User name
-   Username
-   Chat ID
-   Project name
-   Entry file
-   Uploaded project file
-   Project action/status

------------------------------------------------------------------------

## 🛡️ Security Model

``` text
ZIP UPLOAD
    │
    ├── ❌ Absolute paths
    ├── ❌ ../ traversal
    ├── ❌ Symlink entries
    ├── ❌ Outside-project paths
    │
    ▼
SAFE PROJECT DIRECTORY
    │
    ├── 🔒 Project HOME
    ├── 🔒 Project USERPROFILE
    ├── 🔒 Project TEMP
    └── 🔒 Reduced inherited environment
```

> This is a project-level protection layer. For untrusted multi-user
> workloads, OS/container-level sandboxing is still recommended.

------------------------------------------------------------------------

## 🧩 Configuration

The bot expects `config.json` beside `main.py`.

Example:

``` json
{
  "bot_token": "YOUR_BOT_TOKEN",
  "owner_id": 123456789,
  "base_dir": "projects",
  "meta_file": "projects_meta.json",
  "default_online_days": 2,
  "default_project_limit": 1,
  "max_concurrent_projects": 8,
  "queue_enabled": true,
  "auto_restart_default": true,
  "deploy_enabled": true,
  "dynamic_animation_enabled": true,
  "show_live_status": true
}
```

**Never publish your real bot token in GitHub.**

------------------------------------------------------------------------

## 📂 Project Structure

``` text
JXE-HOSTING-HUB/
│
├── main.py
├── config.json
├── projects_meta.json
│
└── projects/
    ├── proj_<chat_id>_<timestamp>/
    │   ├── main.py
    │   ├── .env
    │   └── ...
    │
    └── ...
```

------------------------------------------------------------------------

## ▶️ Quick Start

### 1. Clone

``` bash
git clone https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

### 2. Install dependencies

``` bash
pip install pyTelegramBotAPI requests urllib3 psutil
```

### 3. Create `config.json`

``` json
{
  "bot_token": "YOUR_BOT_TOKEN",
  "owner_id": 123456789,
  "base_dir": "projects",
  "meta_file": "projects_meta.json"
}
```

### 4. Start

``` bash
python main.py
```

The bot connects to Telegram, removes any existing webhook, starts
polling, and automatically reconnects after polling errors.

------------------------------------------------------------------------

## 🧠 Architecture

``` text
                    TELEGRAM
                       │
                       ▼
              ┌─────────────────┐
              │  BOT INTERFACE  │
              ├─────────────────┤
              │ Navigation      │
              │ Callbacks       │
              │ Force Join      │
              │ User Dashboard  │
              │ Admin Panel     │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ PROJECT CONTROL │
              ├─────────────────┤
              │ Deploy          │
              │ Start / Stop    │
              │ Restart         │
              │ Queue / Expiry  │
              │ Files / ENV     │
              │ Backup          │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ RUNTIME MONITOR │
              ├─────────────────┤
              │ Process Tracking│
              │ CPU / RAM       │
              │ Crash Detection │
              │ Auto-Restart    │
              └────────┬────────┘
                       │
                       ▼
                 USER PROJECT
```

------------------------------------------------------------------------

## 💎 Why JXE?

-   ⚡ Telegram-first deployment
-   🚀 Fast project startup
-   📁 Built-in file manager
-   🖥️ Runtime monitoring
-   ♻️ Automatic crash recovery
-   🛡️ ZIP/path safety checks
-   ⏳ Expiry + queue management
-   👑 Powerful admin controls
-   📡 Optional report-group integration
-   ✨ Animated deployment experience

------------------------------------------------------------------------

## 🔥 Final Showcase

![JXE Animated
Banner](https://capsule-render.vercel.app/api?type=venom&height=180&text=JXE%20HOSTING%20HUB&fontSize=42&fontColor=ffffff&stroke=ffffff&strokeWidth=1&color=0:111827,50:4f46e5,100:9333ea&animation=twinkling)

![Final
Animation](https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=800&size=20&pause=600&color=A78BFA&center=true&vCenter=true&width=900&lines=%3C+TELEGRAM+%2B+HOSTING+%2B+CONTROL+%2F%3E;%3C+UPLOAD+%2B+RUN+%2B+MONITOR+%2F%3E;%3C+FILES+%2B+LOGS+%2B+ENV+%2B+BACKUPS+%2F%3E;%3C+AUTO-RESTART+%2B+CRASH-PROTECTION+%2F%3E)

------------------------------------------------------------------------

## 📜 License

Add your preferred license before publishing the repository.

------------------------------------------------------------------------

![Footer](https://capsule-render.vercel.app/api?type=waving&height=140&section=footer&text=Built%20for%20Fast%20Telegram%20Hosting&fontSize=22&fontColor=ffffff&color=0:7c3aed,50:2563eb,100:0f172a&animation=twinkling)

**⭐ If you like JXE Hosting BOT, give the repository a star!**

**JXE HOSTING BOT --- Deploy. Control. Monitor.**
