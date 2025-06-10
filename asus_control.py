import ctypes
from ctypes import c_byte, c_char, c_short, c_int, c_ulonglong
import os
import random
import GPUtil

# Load the DLL
dll_path = os.path.join(os.path.dirname(__file__), "AsusWinIO64.dll")
asus = ctypes.WinDLL(dll_path)

# Define prototypes
asus.InitializeWinIo.argtypes = []
asus.InitializeWinIo.restype = None

asus.ShutdownWinIo.argtypes = []
asus.ShutdownWinIo.restype = None

asus.HealthyTable_FanCounts.argtypes = []
asus.HealthyTable_FanCounts.restype = c_int

asus.HealthyTable_SetFanIndex.argtypes = [c_byte]
asus.HealthyTable_SetFanIndex.restype = None

asus.HealthyTable_FanRPM.argtypes = []
asus.HealthyTable_FanRPM.restype = c_int

asus.HealthyTable_SetFanTestMode.argtypes = [c_char]
asus.HealthyTable_SetFanTestMode.restype = None

asus.HealthyTable_SetFanPwmDuty.argtypes = [c_short]
asus.HealthyTable_SetFanPwmDuty.restype = None

asus.Thermal_Read_Cpu_Temperature.argtypes = []
asus.Thermal_Read_Cpu_Temperature.restype = c_ulonglong


# AsusControl wrapper
class AsusControl:
    def __init__(self):
        asus.InitializeWinIo()

    def __del__(self):
        try:
            asus.ShutdownWinIo()
        except:
            pass  # Don't raise on shutdown

    def set_fan_speed(self, value: int, fan_index: int = 0):
        mode = c_char(b"\x01" if value > 0 else b"\x00")
        asus.HealthyTable_SetFanTestMode(mode)
        asus.HealthyTable_SetFanIndex(c_byte(fan_index))
        asus.HealthyTable_SetFanPwmDuty(c_short(value))

    def set_fan_speed_percent(self, percent: int, fan_index: int = 0):
        value = int((percent / 100.0) * 255)
        self.set_fan_speed(value, fan_index)

    def set_all_fan_speeds(self, value: int):
        fan_count = asus.HealthyTable_FanCounts()
        for fan_index in range(fan_count):
            self.set_fan_speed(value, fan_index)

    def set_all_fan_speeds_percent(self, percent: int):
        value = int((percent / 100.0) * 255)
        self.set_all_fan_speeds(value)

    def get_fan_speed(self, fan_index: int = 0) -> int:
        asus.HealthyTable_SetFanIndex(c_byte(fan_index))
        return asus.HealthyTable_FanRPM()

    def get_all_fan_speeds(self):
        fan_speeds = []
        fan_count = asus.HealthyTable_FanCounts()
        for fan_index in range(fan_count):
            fan_speeds.append(self.get_fan_speed(fan_index))
        return fan_speeds

    def fan_count(self):
        # return 3
        return asus.HealthyTable_FanCounts()

    def cpu_temperature(self) -> int:
        return asus.Thermal_Read_Cpu_Temperature()

    def gpu_temperature(self) -> int:
        gpus = GPUtil.getGPUs()
        return int(max(each.temperature for each in gpus)) if gpus else 0
