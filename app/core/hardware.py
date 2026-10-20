"""Hardware detection and model recommendations."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field


@dataclass
class HardwareInfo:
    os_name: str
    os_version: str
    cpu: str
    ram_gb: float
    gpu_name: str | None = None
    vram_gb: float | None = None
    cuda_available: bool = False
    disk_free_gb: float = 0.0
    recommendation: str = "kokoro"
    notes: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            f"OS: {self.os_name} {self.os_version}",
            f"CPU: {self.cpu}",
            f"RAM: {self.ram_gb:.1f} GB",
            f"Disk free: {self.disk_free_gb:.1f} GB",
        ]
        if self.gpu_name:
            accel = "CUDA" if self.cuda_available else "Detected (CPU fallback may apply)"
            lines.append(f"GPU: {self.gpu_name}")
            lines.append(f"Acceleration: {accel}")
        else:
            lines.append("GPU: None detected")
            lines.append("Acceleration: CPU")
        return lines


def _cpu_name() -> str:
    if platform.system() == "Windows":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            return str(name).strip()
        except Exception:
            pass
    return platform.processor() or platform.machine() or "Unknown CPU"


def _ram_gb() -> float:
    try:
        import psutil

        return psutil.virtual_memory().total / (1024**3)
    except Exception:
        if platform.system() == "Windows":
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(stat)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                return stat.ullTotalPhys / (1024**3)
            except Exception:
                return 8.0
        return 8.0


def _disk_free_gb() -> float:
    try:
        usage = shutil.disk_usage(os.path.expanduser("~"))
        return usage.free / (1024**3)
    except Exception:
        return 0.0


def _gpu_info() -> tuple[str | None, float | None, bool]:
    # Prefer nvidia-smi without requiring CUDA Python packages
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        try:
            import subprocess

            out = subprocess.check_output(
                [
                    nvidia,
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            ).strip()
            if out:
                line = out.splitlines()[0]
                parts = [p.strip() for p in line.split(",")]
                name = parts[0] if parts else "NVIDIA GPU"
                vram = None
                if len(parts) > 1:
                    try:
                        vram = float(parts[1]) / 1024.0
                    except ValueError:
                        vram = None
                cuda = False
                try:
                    import onnxruntime as ort

                    cuda = "CUDAExecutionProvider" in ort.get_available_providers()
                except Exception:
                    cuda = False
                return name, vram, cuda
        except Exception:
            pass
    return None, None, False


def detect_hardware() -> HardwareInfo:
    gpu, vram, cuda = _gpu_info()
    ram = _ram_gb()
    info = HardwareInfo(
        os_name=platform.system(),
        os_version=platform.version(),
        cpu=_cpu_name(),
        ram_gb=ram,
        gpu_name=gpu,
        vram_gb=vram,
        cuda_available=cuda,
        disk_free_gb=_disk_free_gb(),
    )
    if ram < 6:
        info.recommendation = "piper"
        info.notes.append("Limited RAM detected. Piper (lightweight) is recommended.")
        info.notes.append("Kokoro remains optional if you have spare disk and patience.")
    else:
        info.recommendation = "kokoro"
        info.notes.append("Kokoro is recommended for natural voice quality on this system.")
        info.notes.append("Piper is ideal when you need many languages or maximum speed.")
    if info.disk_free_gb and info.disk_free_gb < 2:
        info.notes.append("Low disk space — free at least 2 GB before downloading models.")
    return info
