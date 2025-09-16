A lightweight script that brings smart, automatic tiling to GlazeWM. It runs reliably in the background to create a more fluid and intuitive workflow. **Set it up once and forget about it.**

Unlike other tools, this is a pure Python script. No compiling, no unexpected dependencies—just a simple, reliable service.

If you find it useful, please consider giving the repository a star. 🌟🌟🌟

## Key Features

*   **Smart Tiling**: Analyzes the parent container's shape to make splits more predictable and intuitive, especially in complex layouts.

*   **Rock-Solid Stability**:
    *   **Auto-Reconnect**: Automatically reconnects if GlazeWM restarts.
    *   **Doesn't Crash**: Handles errors gracefully without crashing.
    *   **Clean Shutdown**: Shuts down cleanly, leaving no processes behind.

*   **Lightweight & Unobtrusive**:
    *   **Pure Python**: Easy to run and modify, with no heavy dependencies.
    *   **Silent Operation**: Runs invisibly in the background with no console window.

*   **Optional Statistics**:
    *   **Measures Your Efficiency**: Tracks how many manual tiling adjustments the script saves you over time.
    *   **Local & Optional**: This feature is purely local (no data is sent online) and can be easily disabled with the `--no-stats` flag.

## How to Use

1. Copy the Python script (`.py`) to your local machine.

   * Either rename the extension to `.pyw`,
   * Or download the `.pyw` file directly from this repository.

2. Follow the setup steps below.

---

## Prerequisites

1. **Installed [GlazeWM](https://github.com/glzr-io/glazewm)**

   Enable IPC in your `config.yaml`:

   ```yaml
   ipc:
     enabled: true
   ```

2. **Python environment available**

   * Recommended: use [uv](https://github.com/astral-sh/uv) to create a virtual environment instead of using the global Python installation.
   * Inside the virtual environment, install the dependency:

     ```bash
     pip install websockets
     ```

     or with **uv**:

     ```bash
     uv add websockets       # add to pyproject.toml  
     uv sync                 # install from lockfile
     ```
     or
     ```bash
     uv pip install websockets   # install directly, without writing to pyproject.toml
     ```

3. **Configure GlazeWM startup command**

   Add the following to `general.startup_commands` in `config.yaml` (replace with your actual paths):

   ```yaml
   general:
     startup_commands:
       - 'shell-exec {absolute path to pythonw.exe} {path to your .pyw file}'
   ```

   Example:

   ```yaml
   general:
     startup_commands:
       - 'shell-exec E:/VSCode_User_Code/glaze-wm-tools/.venv/Scripts/pythonw.exe
         E:/VSCode_User_Code/glaze-wm-tools/glaze_autotile.pyw'
   ```
   
   If you want to disable the statistics function, you need to add a parameter after the command.
   `- 'shell-exec E:/VSCode_User_Code/glaze-wm-tools/.venv/Scripts/pythonw.exe E:/VSCode_User_Code/glaze-wm-tools/glaze_autotile.pyw --no-stats'`

5. **About `pythonw.exe` and `.pyw` files**

   * `pythonw.exe`: A “silent” Python interpreter that runs scripts without opening a console window. Perfect for background tasks.
   * `.pyw` file: Same as `.py`, but associated with `pythonw.exe` by default, so it runs quietly without showing a terminal window.

---

## Why this repository does **not** include `pythonw.exe`

Some users may wonder why `pythonw.exe` isn’t bundled here. The reasons are:

1. **Size bloat** – Python itself is large (tens of MB). Including `pythonw.exe` would make the repository unnecessarily heavy.
2. **Platform specific** – `pythonw.exe` only works on Windows, while the repo should remain clean and cross-platform friendly.
3. **Security concerns** – Users generally hesitate to run arbitrary executables from GitHub repositories.
4. **Already included** – Every official Python installation on Windows already provides `pythonw.exe`.

👉 Instead of bundling executables, this project expects you to use a proper Python installation (or a virtual environment via uv), ensuring security and maintainability.
