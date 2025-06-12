import asyncio
from collections import deque
import json
from math import ceil, floor
import subprocess
from typing import Callable
from jsonschema import validate, ValidationError
import os
from PyQt5.QtWidgets import QLayout

from asus_control import AsusControl

settings_schema = {
    "type": "object",
    "properties": {
        "start_with_windows": {"type": "boolean"},
        "fan_sync": {"type": "boolean"},
        "fans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "mode": {"type": "integer", "enum": [0, 1, 2]},
                    "specific_value": {"type": "integer", "minimum": 0, "maximum": 100},
                    "curve_interval": {"type": "integer", "minimum": 1000},
                    "moving_average": {"type": "integer", "minimum": 1},
                    "cpu_curve": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        "minItems": 11,
                        "maxItems": 11,
                    },
                    "gpu_curve": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        "minItems": 11,
                        "maxItems": 11,
                    },
                },
                "required": [
                    "mode",
                    "specific_value",
                    "curve_interval",
                    "moving_average",
                    "cpu_curve",
                    "gpu_curve",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["start_with_windows", "fan_sync", "fans"],
    "additionalProperties": False,
}


def default_settings(fan_count: int):
    return {
        "start_with_windows": False,
        "fan_sync": False,
        "fans": [
            {
                "mode": 0,
                "specific_value": 50,
                "curve_interval": 3000,
                "moving_average": 6,
                "cpu_curve": [
                    [0, 0],
                    [10, 10],
                    [20, 15],
                    [30, 20],
                    [40, 30],
                    [50, 50],
                    [60, 70],
                    [70, 80],
                    [80, 90],
                    [90, 100],
                    [100, 100],
                ],
                "gpu_curve": [
                    [0, 0],
                    [10, 10],
                    [20, 15],
                    [30, 20],
                    [40, 30],
                    [50, 50],
                    [60, 70],
                    [70, 80],
                    [80, 90],
                    [90, 100],
                    [100, 100],
                ],
            }
            for _ in range(fan_count)
        ],
    }


current_dir = os.path.dirname(os.path.abspath(__file__))


def load_settings(fan_count=3):
    try:
        with open(os.path.join(current_dir, "settings.json"), "r") as f:
            data = json.load(f)
            validate(instance=data, schema=settings_schema)
            return data
    except (FileNotFoundError, json.JSONDecodeError, ValidationError) as e:
        print(f"[Warning] Failed to load settings: {e}")
        return default_settings(fan_count)


def save_settings(settings: dict):
    with open(os.path.join(current_dir, "settings.json"), "w") as f:
        json.dump(settings, f)


def clear_layout(layout: QLayout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
        elif item.layout() is not None:
            clear_layout(item.layout())


class MovingAverage:
    def __init__(self, limit: int):
        self.limit = limit
        self.queue = deque()
        self.total = 0

    def push(self, value: int) -> int:
        # Add new value
        self.queue.append(value)
        self.total += value

        # If we've exceeded the window size, pop the oldest
        if len(self.queue) > self.limit:
            removed = self.queue.popleft()
            self.total -= removed

        # Compute and return integer average (floor division)
        return self.total // len(self.queue)


class SetInterval:
    def __init__(self, interval: int, action: Callable):
        self.interval = interval / 1000  # Convert milliseconds to seconds
        self.action = action
        self._task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            await asyncio.sleep(self.interval)
            result = self.action()
            if asyncio.iscoroutine(result):
                await result

    def cancel(self):
        self._task.cancel()


intervals = dict[int, SetInterval]()


def clear_intervals():
    for each in intervals.values():
        each.cancel()
    intervals.clear()


def get_speed_map(curve: list[list[int]]):
    speed_map = dict[int, int]()
    for i in range(1, len(curve)):
        temp1, speed1 = curve[i - 1]
        temp2, speed2 = curve[i]
        a = (speed2 - speed1) / (temp2 - temp1)
        for t in range(temp1, temp2):
            speed_map[t] = ceil(speed1 + (t - temp1) * a)
    return speed_map


def get_speed(speed_map: dict[int, int], temp: int):
    if temp in speed_map:
        return speed_map[temp]
    if temp > 100:
        return 100
    if temp < 0:
        print("Really?")
        return 0
    print(f"Non-integer temperature: {temp}")
    temp1 = floor(temp)
    speed1 = speed_map(temp)
    temp2 = ceil(temp)
    speed2 = speed_map(temp)
    return ceil(speed1 + (temp - temp1) * (speed2 - speed1) * (temp2 - temp1))


def apply_settings(asus: AsusControl, settings: dict):
    validate(instance=settings, schema=settings_schema)
    fan_sync = settings["fan_sync"]

    clear_intervals()

    if fan_sync:
        fan_settings = settings["fans"][0]
        mode = fan_settings["mode"]
        if mode == 0:
            asus.set_all_fan_speeds(0)
        elif mode == 1:
            asus.set_all_fan_speeds_percent(fan_settings["specific_value"])
        else:
            cpu_temp_speed = get_speed_map(fan_settings["cpu_curve"])
            gpu_temp_speed = get_speed_map(fan_settings["gpu_curve"])

            moving_average = fan_settings["moving_average"]
            cpu_ma = MovingAverage(moving_average)
            gpu_ma = MovingAverage(moving_average)

            def action():
                speed = max(
                    get_speed(cpu_temp_speed, cpu_ma.push(asus.cpu_temperature())),
                    get_speed(gpu_temp_speed, gpu_ma.push(asus.gpu_temperature())),
                )
                asus.set_all_fan_speeds_percent(speed)

            intervals[0] = SetInterval(settings["fans"][0]["curve_interval"], action)

    else:
        for i, fan_settings in enumerate(settings["fans"]):
            mode = fan_settings["mode"]
            if mode == 0:
                asus.set_fan_speed(0, i)
            elif mode == 1:
                asus.set_fan_speed_percent(fan_settings["specific_value"], i)
            else:
                cpu_temp_speed = get_speed_map(fan_settings["cpu_curve"])
                gpu_temp_speed = get_speed_map(fan_settings["gpu_curve"])

                moving_average = fan_settings["moving_average"]
                cpu_ma = MovingAverage(moving_average)
                gpu_ma = MovingAverage(moving_average)

                def action():
                    speed = max(
                        get_speed(cpu_temp_speed, cpu_ma.push(asus.cpu_temperature())),
                        get_speed(gpu_temp_speed, gpu_ma.push(asus.gpu_temperature())),
                    )
                    asus.set_fan_speed_percent(speed, i)

                intervals[i] = SetInterval(fan_settings["curve_interval"], action)


def service_apply_settings(asus: AsusControl):
    with open(os.path.join(current_dir, "settings.json"), "r") as f:
        settings = json.load(f)
    if settings["start_with_windows"]:
        apply_settings(asus, settings)
    else:
        unregister()


nssm_path = os.path.join(current_dir, "nssm.exe")


def unregister():
    try:
        subprocess.run([nssm_path, "stop", "AsusFanControl"])
        subprocess.run([nssm_path, "remove", "AsusFanControl", "confirm"])
    except Exception as e:
        return


async def register():
    unregister()
    await asyncio.sleep(3)
    exe_dir = os.path.join(current_dir, "..")
    exe_path = os.path.join(exe_dir, "main.exe")
    subprocess.run(
        [
            nssm_path,
            "install",
            "AsusFanControl",
            exe_path,
            "--service",
        ]
    )
    subprocess.run([nssm_path, "start", "AsusFanControl"])


async def cleanup(asus: AsusControl):
    clear_intervals()
    asus.set_all_fan_speeds(0)
    asus.__del__()
    await register()
