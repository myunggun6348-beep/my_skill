from __future__ import annotations

import importlib.util
import json
import platform
import sys
import winreg


PACKAGES = {"fitz": "PyMuPDF", "PIL": "Pillow", "yaml": "PyYAML", "lxml": "lxml", "win32com": "pywin32"}


def check() -> dict:
    result = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "packages": {name: bool(importlib.util.find_spec(module)) for module, name in PACKAGES.items()},
        "hancom_com_registered": False,
        "hancom_com_live_probe": "not-run",
        "errors": [],
    }
    if platform.system() != "Windows":
        result["errors"].append("MVP HWPX generation requires Windows.")
        return result
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"HWPFrame.HwpObject\CLSID") as key:
            result["hancom_com_registered"] = bool(winreg.QueryValueEx(key, None)[0])
    except OSError as exc:
        result["errors"].append(f"Hancom COM registration not found: {exc}")
    if result["hancom_com_registered"]:
        result["hancom_com_live_probe"] = "deferred-to-integration-test"
    return result


def main() -> int:
    result = check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(result["packages"].values()) and result["hancom_com_registered"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
