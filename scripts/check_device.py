"""Answers one question: what on-device AI path can this machine actually run?

Run this first:  python scripts/check_device.py

Deliberately conservative. A wrong 'yes' here costs you days chasing a runtime
your silicon cannot reach, so anything unrecognised is reported as unknown
rather than optimistically assumed.
"""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys

# Microsoft's Copilot+ bar. Below this, Windows keeps its built-in
# on-device model features locked regardless of the rest of the machine.
COPILOT_PLUS_MIN_TOPS = 40

# Intel Core Ultra families.
#
# Note on Meteor Lake: Foundry Local's documentation lists Arrow Lake as the
# minimum for its Intel NPU execution provider, but a Core Ultra 7 165H was
# observed loading 'phi-4-mini-instruct-openvino-npu' onto its NPU
# successfully. The documented floor is more conservative than the behaviour,
# so this reports it as usable and tells you how to confirm it yourself.
INTEL_FAMILIES = [
    # (regex on model number, family, approx NPU TOPS, npu usable by OpenVINO EP)
    (r"\b1\d{2}[HUV]\b", "Meteor Lake (Core Ultra Series 1)", 11, True),
    (r"\b2\d{2}[HUV]\b", "Arrow Lake / Lunar Lake (Core Ultra Series 2)", 45, True),
]

QUALCOMM_HINT = ("snapdragon", "oryon")
AMD_AI_HINT = ("ryzen ai",)


def _powershell(cmd: str) -> str:
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        return ""
    try:
        out = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=45,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def cpu_name() -> str:
    if platform.system() == "Windows":
        name = _powershell("(Get-CimInstance Win32_Processor | Select-Object -First 1).Name")
        if name:
            return name.strip()
    return platform.processor() or platform.machine() or "unknown"


def total_ram_gb() -> float | None:
    if platform.system() == "Windows":
        raw = _powershell("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
        if raw.strip().isdigit():
            return round(int(raw.strip()) / 1024**3, 1)
    try:
        import os
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except Exception:
        return None


def npu_devices() -> list[str]:
    if platform.system() != "Windows":
        return []
    raw = _powershell(
        "Get-CimInstance Win32_PnPEntity | "
        # \b matters: without it 'USB Input Device' matches, because
        # 'iNPUt' contains 'npu'.
        "Where-Object { $_.Name -match '\\bNPU\\b|Neural Process|AI Boost|Hexagon|Compute Accelerator' } | "
        "Select-Object -ExpandProperty Name"
    )
    return sorted({ln.strip() for ln in raw.splitlines() if ln.strip()})


def gpus() -> list[str]:
    if platform.system() != "Windows":
        return []
    raw = _powershell("Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name")
    return sorted({ln.strip() for ln in raw.splitlines() if ln.strip()})


def classify_npu(cpu: str) -> tuple[str, int | None, bool | None]:
    """Return (family, approx TOPS, whether a local runtime can target the NPU)."""
    lc = cpu.lower()
    if "core ultra" in lc or "core(tm) ultra" in lc:
        for pattern, family, tops, usable in INTEL_FAMILIES:
            if re.search(pattern, cpu, re.IGNORECASE):
                return family, tops, usable
        return "Intel Core Ultra (unrecognised model)", None, None
    if any(h in lc for h in QUALCOMM_HINT):
        return "Qualcomm Snapdragon X", 45, True
    if any(h in lc for h in AMD_AI_HINT):
        return "AMD Ryzen AI", 50, True
    return "no recognised NPU family", None, False


def gpu_path(gpu_list: list[str]) -> tuple[str, str]:
    """Which local-runtime GPU acceleration applies, and can it run Phi Silica?

    Phi Silica's supported GPUs are NVIDIA RTX 30-series+ and AMD RX 9060+,
    both with 6+ GB vRAM. Intel GPUs accelerate local runtimes but are not on
    that list.
    """
    joined = " ".join(gpu_list).lower()
    if "nvidia" in joined or "geforce" in joined or "rtx" in joined:
        return "NVIDIA - CUDA / TensorRT execution provider", "possible (RTX 30+ with 6GB+ vRAM)"
    if "radeon" in joined:
        return "AMD - Vitis AI / DirectML", "possible (RX 9060+ with 6GB+ vRAM)"
    if "intel" in joined and ("arc" in joined or "iris" in joined or "graphics" in joined):
        return "Intel - OpenVINO GPU execution provider", "no (Intel GPUs not supported)"
    return "generic - WebGPU / DirectML fallback", "no"


def foundry_version() -> str | None:
    exe = shutil.which("foundry")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
        text = (out.stdout or out.stderr).strip()
        return text.splitlines()[0] if text else exe
    except Exception:
        return exe


def main() -> int:
    cpu = cpu_name()
    npus = npu_devices()
    gpu_list = gpus()
    ram = total_ram_gb()

    family, tops, npu_usable = classify_npu(cpu)
    accel, phi_silica = gpu_path(gpu_list)
    copilot_plus = (tops is not None and tops >= COPILOT_PLUS_MIN_TOPS)

    report = {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": cpu,
        "ram_gb": ram,
        "npu_present": npus or None,
        "npu_family": family,
        "npu_tops_approx": tops,
        "npu_usable_by_local_runtime": npu_usable,
        "copilot_plus_class": copilot_plus,
        "gpus": gpu_list,
        "gpu_acceleration": accel,
        "phi_silica_supported": phi_silica,
        "foundry_cli": foundry_version(),
    }
    print(json.dumps(report, indent=2))

    print("\n" + "=" * 64)
    if copilot_plus and npu_usable:
        print("VERDICT: NPU PATH - Copilot+ class. Local runtime can target the NPU.")
    elif npu_usable:
        print("VERDICT: NPU PATH - a local runtime can target this NPU.")
        print(f"         {family}" + (f", approx {tops} TOPS." if tops else "."))
        print(f"         Below the {COPILOT_PLUS_MIN_TOPS} TOPS Copilot+ bar, so Windows'")
        print("         built-in on-device model APIs stay locked - but a portable")
        print("         runtime still uses the NPU. Confirm it: load a model, then")
        print("         watch Task Manager > Performance > NPU while generating.")
    elif npus and npu_usable is False:
        print("VERDICT: GPU PATH - an NPU exists but no local runtime can address it.")
        print(f"         {family}" + (f", approx {tops} TOPS." if tops else "."))
        print(f"         Copilot+ needs {COPILOT_PLUS_MIN_TOPS} TOPS, so Windows' built-in")
        print("         on-device model APIs stay locked. Use the GPU instead:")
        print(f"         {accel}")
    else:
        print("VERDICT: CPU/GPU PATH - no usable NPU detected.")
        print(f"         {accel}")

    print(f"\n  Phi Silica on this machine: {phi_silica}")
    print("  Note: Phi Silica is being replaced by Aion Instruct (Nov 2026).")
    print("        Prefer a portable local runtime over the built-in Windows APIs.")

    if ram is not None:
        if ram >= 24:
            print(f"\n  {ram} GB RAM - comfortable. Try a 3B-4B model, not just 0.5B.")
        elif ram >= 16:
            print(f"\n  {ram} GB RAM - fine. 1.5B models should run well.")
        else:
            print(f"\n  WARNING: {ram} GB RAM - stay on a 0.5B model.")

    if not report["foundry_cli"]:
        print("\n  Local runtime not detected on PATH.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
