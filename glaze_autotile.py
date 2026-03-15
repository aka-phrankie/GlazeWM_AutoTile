import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

import websockets

# ==============================================================================
# 配置与模型 (Configuration & Models)
# ==============================================================================
DEFAULT_CONFIG = {
    "core": {
        "ws_uri": "ws://localhost:6123",
        "debounce_delay_ms": 200,
        "log_level": "INFO",
    }
}


@dataclass
class Window:
    id: str
    width: int
    height: int
    hasFocus: bool

    @classmethod
    def from_dict(cls, data: dict) -> "Window":
        return cls(
            id=data.get("id", ""),
            width=data.get("width", 0),
            height=data.get("height", 0),
            hasFocus=data.get("hasFocus", False),
        )


@dataclass
class Workspace:
    id: str
    name: str
    children_raw: List[Dict[str, Any]]

    def get_tiling_windows(self) -> List[Window]:
        """递归获取所有平铺状态的子窗口"""
        wins = []

        def _traverse(node):
            if "children" in node:
                for child in node["children"]:
                    if child.get("type") == "window":
                        state = child.get("state", {})
                        state_type = (
                            state.get("type") if isinstance(state, dict) else state
                        )
                        if state_type == "tiling":
                            wins.append(Window.from_dict(child))
                    else:
                        _traverse(child)

        _traverse({"children": self.children_raw})
        return wins


# ==============================================================================
# 核心逻辑 (Core Engine)
# ==============================================================================
class GlazeWMClient:
    def __init__(self, uri: str):
        self.uri = uri
        self.ws: Any = None
        self.message_queue = asyncio.Queue()

    @property
    def is_connected(self) -> bool:
        return self.ws is not None and self.ws.state == websockets.protocol.State.OPEN

    async def connect(self):
        self.ws = await websockets.connect(self.uri)
        asyncio.create_task(self._receive_loop())

    async def _receive_loop(self):
        if not self.ws:
            return
        try:
            async for msg in self.ws:
                await self.message_queue.put(msg)
        except Exception:
            pass

    async def send_command(self, cmd: str) -> None:
        if self.is_connected:
            await self.ws.send(f"command {cmd}")

    async def query(self, query_str: str) -> dict:
        if not self.is_connected:
            return {}
        await self.ws.send(query_str)
        while True:
            try:
                msg = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                event_data = json.loads(msg)
                if event_data.get("messageType") == "client_response":
                    return event_data
            except asyncio.TimeoutError:
                # If a timeout occurs, continue the loop to try getting a message again.
                # This prevents immediate exit on query timeout.
                continue
            except Exception:
                # For any other exception (e.g., JSON decoding error), return an empty dict.
                return {}


class AutoTilerApp:
    def __init__(self, config: dict):
        self.config = config
        self.client = GlazeWMClient(config["core"]["ws_uri"])
        self.workspace_states: Dict[str, set] = {}

        # 统计数据初始化
        self.stats: Dict[str, Any] = {"total_guidance": 0}
        if os.path.exists("auto_tiler_stats.json"):
            try:
                with open("auto_tiler_stats.json", "r") as f:
                    self.stats.update(json.load(f))
            except Exception:
                pass

    def save_stats(self):
        """持久化统计数据到文件"""
        try:
            with open("auto_tiler_stats.json", "w") as f:
                json.dump(self.stats, f)
        except Exception:
            pass

    async def run(self):
        try:
            await self.client.connect()
            for ev in [
                "window_managed",
                "focus_changed",
                "workspace_activated",
                "focused_container_moved",
            ]:
                await self.client.ws.send(f"sub -e {ev}")

            debounce = self.config["core"]["debounce_delay_ms"] / 1000.0
            while True:
                try:
                    msg = await asyncio.wait_for(
                        self.client.message_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                event_data = json.loads(msg)

                if event_data.get("messageType") in (
                    "event_subscription",
                    "event_subscription_message",
                ):
                    event_type = event_data.get("data", {}).get("eventType", "unknown")
                    await asyncio.sleep(debounce)
                    # 清空积压消息
                    while not self.client.message_queue.empty():
                        self.client.message_queue.get_nowait()
                    await self._apply_guidance(event_type)
        except Exception as e:
            if not isinstance(e, asyncio.TimeoutError):
                pass
        finally:
            self.save_stats()  # 退出前强制保存一次
            if self.client.ws:
                await self.client.ws.close()

    async def _apply_guidance(self, event_type: str):
        res = await self.client.query("query workspaces")
        workspaces = res.get("data", {}).get("workspaces", [])
        active_ws_data = next((w for w in workspaces if w.get("hasFocus")), None)
        if not active_ws_data:
            return

        ws = Workspace(
            active_ws_data["id"],
            active_ws_data["name"],
            active_ws_data.get("children", []),
        )
        wins = ws.get_tiling_windows()
        current_ids = {w.id for w in wins}

        # 判断是否需要更新 (由于只针对焦点窗口引导，任何触发事件都会处理焦点窗口)
        focused_win = next((w for w in wins if w.hasFocus), None)
        if focused_win:
            ratio = (
                focused_win.width / focused_win.height
                if focused_win.height > 0
                else 1.0
            )
            direction = "horizontal" if ratio > 1.0 else "vertical"
            await self.client.send_command(f"set-tiling-direction {direction}")

            # 更新统计并保存 (兼容旧版 TotalSwitches 和 DailySwitches 字段)
            today = datetime.now().strftime("%Y-%m-%d")

            # 1. 更新总数
            self.stats["TotalSwitches"] = int(self.stats.get("TotalSwitches", 0)) + 1
            self.stats["total_guidance"] = int(self.stats.get("total_guidance", 0)) + 1

            # 2. 更新每日统计
            daily = self.stats.get("DailySwitches", {})
            if not isinstance(daily, dict):
                daily = {}
            daily[today] = int(daily.get(today, 0)) + 1
            self.stats["DailySwitches"] = daily

            # 每 10 次保存一次，减少 IO
            if self.stats["total_guidance"] % 10 == 0:
                self.save_stats()

        self.workspace_states[ws.id] = current_ids


def main():
    app = AutoTilerApp(DEFAULT_CONFIG)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
