from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path


def recognize_formula(image: Path, config: dict) -> dict:
    provider = config.get("provider", "none")
    if provider in {"none", "text-layer"}:
        return {"latex": "", "confidence": 0.0, "reason": f"Provider {provider} does not OCR image formulas"}
    if provider != "external-command":
        return {"latex": "", "confidence": 0.0, "reason": f"Unknown provider: {provider}"}
    command = str(config.get("external_command", "")).strip()
    if not command:
        return {"latex": "", "confidence": 0.0, "reason": "external_command is empty"}
    argv = [part.replace("{image}", str(image)) for part in shlex.split(command, posix=False)]
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=120, check=False)
    if completed.returncode != 0:
        return {"latex": "", "confidence": 0.0, "reason": completed.stderr.strip() or "OCR command failed"}
    try:
        payload = json.loads(completed.stdout)
        return {"latex": str(payload["latex"]), "confidence": float(payload.get("confidence", 0.0)), "reason": ""}
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"latex": "", "confidence": 0.0, "reason": f"Invalid OCR JSON: {exc}"}

