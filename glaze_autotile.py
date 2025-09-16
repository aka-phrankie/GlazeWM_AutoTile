import argparse
import asyncio
import functools
import json
import logging
import os
import sys
from abc import ABC, abstractmethod
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

# Ensure websockets is installed.
try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:
    print(
        "Error: 'websockets' library is not installed. Please use 'pip install websockets' to install it.",
        file=sys.stderr,
    )
    sys.exit(1)

# Create a special block that only runs during type checking.
if TYPE_CHECKING:
    from websockets.client import WebSocketClientProtocol  # type: ignore


# --- Configuration ---
class Config:
    """Centralizes all configuration parameters."""

    WEBSOCKET_URI = "ws://localhost:6123"
    LOG_FILE = "auto_tiler.log"
    STATS_FILE = "auto_tiler_stats.json"
    INTENT_DELAY = 0.2
    STATS_SAVE_INTERVAL = 60
    INITIAL_RECONNECT_DELAY = 5
    MAX_RECONNECT_DELAY = 60
    RECONNECT_BACKOFF_FACTOR = 2
    EVENT_FOCUS_CHANGED = "focus_changed"
    EVENT_WINDOW_MANAGED = "window_managed"
    EVENT_APP_EXITING = "application_exiting"
    CMD_SET_TILING_DIRECTION = "command set-tiling-direction"


# --- Decorators ---
def log_and_handle_exceptions(func):
    """A decorator to automatically log method execution and handle common exceptions."""

    @functools.wraps(func)
    async def wrapper(instance, *args, **kwargs):
        logger = getattr(instance, "logger", logging)
        try:
            return await func(instance, *args, **kwargs)
        except ConnectionClosed:
            logger.warning(f"Connection closed during '{func.__name__}'.")
            raise
        except Exception as e:
            logger.error(
                f"An unexpected error occurred in {func.__name__}: {e}", exc_info=True
            )

    return wrapper


# --- Strategy Pattern ---
class TilingStrategy(ABC):
    """Abstract base class for tiling strategies, defining the decision-making interface."""

    @abstractmethod
    def determine_direction(self, container: dict | None) -> str | None:
        pass


class ParentPriorityShapeStrategy(TilingStrategy):
    """A concrete strategy implementation: Prioritizes the parent container's shape to determine the tiling direction."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def determine_direction(self, container: dict | None) -> str | None:
        if not container:
            return None
        parent = container.get("parent")
        decision_container = (
            parent if parent and parent.get("layout") == "tiling" else container
        )
        if decision_container is parent:
            self.logger.debug("Decision based on [Parent Container]'s shape.")
        else:
            self.logger.debug(
                "Decision based on [Current Window]'s shape (no tiling parent)."
            )
        width, height = (
            decision_container.get("width"),
            decision_container.get("height"),
        )
        if width is not None and height is not None:
            return "vertical" if height > width else "horizontal"
        return None


# --- Core Logic & Observer Pattern ---
class GlazeWMClient:
    """The core business logic class, acting as the "Publisher"."""

    def __init__(
        self, config: Config, strategy: TilingStrategy, logger: logging.Logger
    ):
        self.config, self.strategy, self.logger = config, strategy, logger
        self._websocket: "WebSocketClientProtocol | None" = None
        self._current_direction: str | None = None
        self._set_direction_task: asyncio.Task | None = None
        self._subscribers = {config.EVENT_WINDOW_MANAGED: []}

    def subscribe(self, event_type: str, callback):
        if event_type in self._subscribers:
            subscriber_name = getattr(callback, "__self__", callback).__class__.__name__
            self.logger.info(f"'{subscriber_name}' subscribed to '{event_type}'.")
            self._subscribers[event_type].append(callback)

    async def _publish(self, event_type: str, data: dict):
        if event_type in self._subscribers:
            self.logger.debug(
                f"Publishing event '{event_type}' to {len(self._subscribers[event_type])} subscribers."
            )
            await asyncio.gather(
                *(callback(data) for callback in self._subscribers[event_type])
            )

    async def _set_direction_after_delay(self, direction: str):
        await asyncio.sleep(self.config.INTENT_DELAY)
        if self._websocket and direction != self._current_direction:
            try:
                await self._websocket.send(
                    f"{self.config.CMD_SET_TILING_DIRECTION} {direction}"
                )
                self._current_direction = direction
                self.logger.debug(f"Tiling direction preset to '{direction}'.")
            except ConnectionClosed:
                self.logger.warning(
                    f"Could not set tiling direction to '{direction}' because connection was closed."
                )
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred while setting tiling direction: {e}"
                )

    @log_and_handle_exceptions
    async def _on_focus_changed(self, data: dict):
        if self._set_direction_task and not self._set_direction_task.done():
            self._set_direction_task.cancel()
        container = data.get("data", {}).get("focusedContainer")
        if new_direction := self.strategy.determine_direction(container):
            self._set_direction_task = asyncio.create_task(
                self._set_direction_after_delay(new_direction)
            )

    @log_and_handle_exceptions
    async def _on_window_managed(self, data: dict):
        await self._publish(self.config.EVENT_WINDOW_MANAGED, data)

    async def run(self):
        delay = self.config.INITIAL_RECONNECT_DELAY
        events = [
            self.config.EVENT_FOCUS_CHANGED,
            self.config.EVENT_WINDOW_MANAGED,
            self.config.EVENT_APP_EXITING,
        ]
        while True:
            try:
                self.logger.info(
                    f"Attempting to connect to GlazeWM: {self.config.WEBSOCKET_URI}..."
                )
                async with websockets.connect(self.config.WEBSOCKET_URI) as websocket:
                    self.logger.info("Successfully connected to GlazeWM IPC.")
                    delay, self._websocket, self._current_direction = (
                        self.config.INITIAL_RECONNECT_DELAY,
                        websocket,
                        None,
                    )
                    for event in events:
                        await websocket.send(f"sub -e {event}")
                    self.logger.info(f"Subscribed to events: {', '.join(events)}")
                    async for message in websocket:
                        response = json.loads(message)
                        event_type = response.get("data", {}).get("eventType")
                        if event_type == self.config.EVENT_FOCUS_CHANGED:
                            await self._on_focus_changed(response)
                        elif event_type == self.config.EVENT_WINDOW_MANAGED:
                            await self._on_window_managed(response)
                        elif event_type == self.config.EVENT_APP_EXITING:
                            self.logger.info(
                                "GlazeWM is exiting. Shutting down the script."
                            )
                            return
            except (ConnectionRefusedError, OSError) as e:
                self.logger.error(f"Connection failed: {e}. Retrying in {delay}s...")
            except ConnectionClosed:
                self.logger.warning(f"Connection lost. Retrying in {delay}s...")
            except Exception as e:
                self.logger.error(
                    f"An unexpected error: {e}. Retrying in {delay}s...", exc_info=True
                )
            await asyncio.sleep(delay)
            delay = min(
                self.config.MAX_RECONNECT_DELAY,
                delay * self.config.RECONNECT_BACKOFF_FACTOR,
            )


# --- Statistics Module (Subscriber) ---
class StatsManager:
    """Manages, loads, and saves script execution statistics in a non-blocking manner."""

    KEY_ORDER = [
        "TotalSwitches",
        "AuthorMessage",
        "FirstInstallTime",
        "Tip",
        "DailySwitches",
    ]

    def __init__(self, filepath: str, logger: logging.Logger):
        self.filepath, self.logger, self._lock = filepath, logger, asyncio.Lock()
        self.stats = self._load_stats_blocking()

        needs_initial_save = False
        if "FirstInstallTime" not in self.stats:
            self.stats["FirstInstallTime"] = datetime.now().isoformat(
                sep=" ", timespec="seconds"
            )
            needs_initial_save = True

        if "AuthorMessage" not in self.stats:
            self.stats["AuthorMessage"] = (
                "Thank you for using this script. To support its development and the core GlazeWM project, "
                "please consider starring the repositories on GitHub: "
                "[Script] https://github.com/aka-phrankie/GlazeWM_AutoTile and "
                "[Official] https://github.com/glzr-io/glazewm"
            )
            needs_initial_save = True
        if "Tip" not in self.stats:
            self.stats["Tip"] = (
                "The 'DailySwitches' data can be used with data analysis tools or AI to visualize "
                "your window management activity."
            )
            needs_initial_save = True

        if needs_initial_save:
            self.logger.info("First run detected. Initializing stats file.")
            self._save_stats_blocking()

        self._reconcile_totals()

    def _reconcile_totals(self):
        """Reconciles and corrects totals on startup, safely handling and converting numeric strings."""
        try:
            if "DailySwitches" in self.stats and self.stats["DailySwitches"]:
                calculated_total = 0
                for day, value in self.stats["DailySwitches"].items():
                    try:
                        numeric_value = int(value)
                        if self.stats["DailySwitches"][day] is not numeric_value:
                            self.stats["DailySwitches"][day] = numeric_value
                        calculated_total += numeric_value
                    except (ValueError, TypeError):
                        self.logger.warning(
                            f"Skipping non-numeric value '{value}' for day '{day}'."
                        )

                recorded_total = self.stats.get("TotalSwitches", 0)
                if calculated_total != recorded_total:
                    self.logger.warning(
                        f"Total switches mismatch! Recorded: {recorded_total}, Calculated: {calculated_total}. Correcting."
                    )
                    self.stats["TotalSwitches"] = calculated_total
        except Exception as e:
            self.logger.error(f"Error during stats reconciliation: {e}", exc_info=True)

    async def on_window_managed(self, event_data: dict):
        self._increment()

    def _increment(self):
        today = date.today().isoformat()
        self.stats["TotalSwitches"] = self.stats.get("TotalSwitches", 0) + 1
        daily_stats = self.stats.setdefault("DailySwitches", {})
        daily_stats[today] = daily_stats.get(today, 0) + 1

        # Log the window management event and the updated count.
        self.logger.info(
            f"GlazeWM managed a new window. Incrementing stats. Today's count: {daily_stats[today]}"
        )

    async def save(self):
        await asyncio.to_thread(self._save_stats_blocking)

    async def run_periodic_save(self, interval: int):
        while True:
            await asyncio.sleep(interval)
            await self.save()

    def _load_stats_blocking(self) -> dict:
        """Loads statistics from the file."""
        if not os.path.exists(self.filepath):
            self.logger.info("Stats file not found. Starting fresh.")
            return {"TotalSwitches": 0, "DailySwitches": {}}
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                stats_data = json.load(f)
                total = stats_data.get("TotalSwitches", 0)
                self.logger.info(f"Stats loaded. Total switches: {total}")
                return stats_data
        except (json.JSONDecodeError, IOError, TypeError) as e:
            self.logger.error(
                f"Could not load or parse stats file: {e}. Starting fresh."
            )
            return {"TotalSwitches": 0, "DailySwitches": {}}

    def _save_stats_blocking(self):
        """
        The actual blocking file write operation.
        Before writing, it sorts the dictionary keys according to KEY_ORDER.
        """
        ordered_stats = {
            key: self.stats[key] for key in self.KEY_ORDER if key in self.stats
        }

        for key, value in self.stats.items():
            if key not in ordered_stats:
                ordered_stats[key] = value

        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(ordered_stats, f, indent=2)
            self.logger.info("Stats successfully saved to disk.")
        except IOError as e:
            self.logger.error(f"Could not save stats: {e}")


# --- Program Entry Point & Assembly ---
def setup_logging(log_file: str, script_dir: str) -> logging.Logger:
    log_path = os.path.join(script_dir, log_file)
    log_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s"
    )
    handler = RotatingFileHandler(
        log_path, maxBytes=1 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(log_formatter)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)
    if sys.executable.endswith("python.exe"):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        logger.addHandler(console_handler)
    return logger


async def main():
    parser = argparse.ArgumentParser(
        description="GlazeWM Auto Tiler with optional stats."
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="Disable the statistics counting feature.",
    )
    args = parser.parse_args()
    script_dir = (
        os.path.dirname(sys.executable)
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))
    )
    config = Config()
    logger = setup_logging(config.LOG_FILE, script_dir)

    logger.info("Starting GlazeWM Auto Tiler script...")

    tiling_strategy = ParentPriorityShapeStrategy(logger)
    client = GlazeWMClient(config, tiling_strategy, logger)
    stats_manager = None
    if not args.no_stats:
        stats_file_path = os.path.join(script_dir, config.STATS_FILE)
        stats_manager = StatsManager(stats_file_path, logger)
        if install_time := stats_manager.stats.get("FirstInstallTime"):
            logger.info(f"Script first installed on: {install_time}")
        client.subscribe(config.EVENT_WINDOW_MANAGED, stats_manager.on_window_managed)
        logger.info("Statistics feature is ENABLED.")
    else:
        logger.info("Statistics feature is DISABLED.")

    tasks = {asyncio.create_task(client.run())}
    if stats_manager:
        tasks.add(
            asyncio.create_task(
                stats_manager.run_periodic_save(config.STATS_SAVE_INTERVAL)
            )
        )
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if exc := task.exception():
                logger.error("A core task exited with an exception:", exc_info=exc)
    finally:
        logger.info("Initiating shutdown sequence...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if stats_manager:
            logger.info("Executing final stats save...")
            await stats_manager.save()
        logger.info("Script has stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.getLogger().info("Script interrupted by user or system. Shutting down.")
