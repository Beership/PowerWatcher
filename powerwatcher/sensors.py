"""Cheap, dependency-free Windows sensors.

CPU utilisation comes from psutil; GPU power comes from NVML (in-process
driver call) when an NVIDIA driver is present, with an nvidia-smi subprocess
as fallback. No kernel drivers, no admin rights.
"""
from __future__ import annotations

import ctypes
import shutil
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass

import psutil

CREATE_NO_WINDOW = 0x08000000
_SMI_CACHE_S = 8.0

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_kernel32.GetTickCount.restype = wintypes.DWORD
_kernel32.GetTickCount64.restype = ctypes.c_ulonglong


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds() -> float:
    """Seconds since the last keyboard/mouse input."""
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    tick = _kernel32.GetTickCount() & 0xFFFFFFFF
    return ((tick - info.dwTime) & 0xFFFFFFFF) / 1000.0


def tick_seconds() -> float:
    """Monotonic uptime in seconds. Does NOT advance while the PC sleeps."""
    return _kernel32.GetTickCount64() / 1000.0


# --------------------------------------------------------------------- NVML
class _NvmlUtilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("mem", ctypes.c_uint)]


def _check(ret: int) -> None:
    if ret != 0:  # NVML_SUCCESS
        raise OSError(f"nvml error {ret}")


class _Nvml:
    """In-process NVML binding: no subprocess spawn, no output parsing."""

    def __init__(self) -> None:
        dll = ctypes.CDLL("nvml.dll")
        try:
            _check(dll.nvmlInit_v2())
        except AttributeError:
            _check(dll.nvmlInit())
        get_handle = getattr(dll, "nvmlDeviceGetHandleByIndex_v2", None) or getattr(
            dll, "nvmlDeviceGetHandleByIndex"
        )
        self.dll = dll
        self.handle = ctypes.c_void_p()
        _check(get_handle(0, ctypes.byref(self.handle)))
        self.dll.nvmlDeviceGetPowerUsage.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint),
        ]
        self.dll.nvmlDeviceGetUtilizationRates.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_NvmlUtilization),
        ]

    def read(self) -> "GpuReading":
        milliwatts = ctypes.c_uint()
        _check(self.dll.nvmlDeviceGetPowerUsage(self.handle, ctypes.byref(milliwatts)))
        util = _NvmlUtilization()
        try:
            self.dll.nvmlDeviceGetUtilizationRates(self.handle, ctypes.byref(util))
            gpu_pct: float | None = float(util.gpu)
        except OSError:
            gpu_pct = None
        return GpuReading(
            power_w=milliwatts.value / 1000.0, util_pct=gpu_pct, source="nvml"
        )


# -------------------------------------------------------------------- probes
@dataclass
class GpuReading:
    power_w: float | None = None
    util_pct: float | None = None
    source: str = "none"  # nvml | nvidia-smi | none


class GpuProbe:
    """NVML first; nvidia-smi subprocess only as a fallback."""

    def __init__(self) -> None:
        self._nvml: _Nvml | None = None
        try:
            self._nvml = _Nvml()
        except (OSError, AttributeError):
            self._nvml = None
        self.exe = None if self._nvml else shutil.which("nvidia-smi")
        self.available = self._nvml is not None or self.exe is not None
        self._last_ts = 0.0
        self._last = GpuReading()
        self.error: str | None = None

    def read(self, force: bool = False) -> GpuReading:
        if self._nvml is not None:
            try:
                return self._nvml.read()
            except OSError as exc:
                # Driver hiccup: drop to the subprocess path rather than dying.
                self.error = str(exc)[:200]
                self._nvml = None
                self.exe = shutil.which("nvidia-smi")
                self.available = self.exe is not None
        return self._read_smi(force)

    def _read_smi(self, force: bool) -> GpuReading:
        if not self.exe:
            return GpuReading()
        now = time.monotonic()
        if not force and now - self._last_ts < _SMI_CACHE_S:
            return self._last
        self._last_ts = now
        try:
            proc = subprocess.run(
                [
                    self.exe,
                    "--query-gpu=power.draw,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=CREATE_NO_WINDOW,
            )
            if proc.returncode != 0:
                self.error = (proc.stderr or "").strip()[:200]
                return self._last
            first = (proc.stdout or "").strip().splitlines()[0]
            power_s, util_s = [x.strip() for x in first.split(",")[:2]]
            self._last = GpuReading(
                power_w=float(power_s),
                util_pct=float(util_s),
                source="nvidia-smi",
            )
            self.error = None
        except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
            self.error = str(exc)[:200]
            self.available = False
        return self._last


class CpuProbe:
    def __init__(self) -> None:
        self._primed = False

    def read(self) -> tuple[float, float]:
        """Returns (overall utilisation %, busiest-single-core %).

        The second value keeps a one-core load (6% overall on a 16-thread CPU)
        from being modelled as if the whole package were nearly idle.
        """
        if not self._primed:
            psutil.cpu_percent(interval=None, percpu=True)
            self._primed = True
            return 0.0, 0.0
        per = psutil.cpu_percent(interval=None, percpu=True)
        if not per:
            return 0.0, 0.0
        return sum(per) / len(per), max(per)


# --------------------------------------------------------- foreground window
def foreground_process() -> str | None:
    """Executable name of the app currently in the foreground, or None."""
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD(0)
    if not _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or not pid.value:
        return None
    try:
        return psutil.Process(pid.value).name()
    except psutil.Error:
        return None


def _cim(cls: str, prop: str) -> str:
    """One-off WMI query; only used on first run to prefill the model."""
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance {cls} | Select-Object -First 1).{prop}",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        return (proc.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def detect_hardware_names() -> dict[str, str]:
    return {
        "cpu": _cim("Win32_Processor", "Name"),
        "gpu": _cim("Win32_VideoController", "Name"),
    }
