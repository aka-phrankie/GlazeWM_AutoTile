# GlazeWM AutoTile

A lightweight helper script that works with [GlazeWM](https://github.com/glzr-io/glazewm) to automatically adjust tiling direction.
It connects to GlazeWM’s IPC WebSocket API, listens for window events, and toggles the tiling direction when windows are too small.

Unlike other implementations, **no heavy dependencies, no compilation, no binaries** — just Python + one library.

---

## Features

* Listens to GlazeWM’s `window_managed` event.
* Detects tiling size of newly managed windows.
* If a window’s tiling size is below a threshold (default: `<= 0.5`), automatically runs:

  ```
  command toggle-tiling-direction
  ```
* Runs silently in the background with `pythonw.exe`.

---

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

4. **About `pythonw.exe` and `.pyw` files**

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

---

## FAQ

**Q: Can I change the size threshold (default `0.5`)?**
A: Yes. Modify the value inside the script to suit your workflow.

**Q: Do I need to compile this script into an `.exe`?**
A: No. Just use Python directly with `pythonw.exe`. That’s why the tool is so lightweight.
