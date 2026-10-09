from __future__ import annotations

import multiprocessing
import time
import uuid
from pathlib import Path


def _export_worker(output: str, visible: bool, connection):
    from build_hwpx import HangulBuilder
    import win32process

    builder = None
    try:
        builder = HangulBuilder(visible=visible)
        pid = win32process.GetWindowThreadProcessId(builder.hwp.XHwpWindows.Item(0).WindowHandle)[1]
        connection.send(("pid", pid))
        path = Path(output)
        if not builder.hwp.Open(str(path), "HWPX", "forceopen:true"):
            raise RuntimeError("Hancom could not reopen the positioned HWPX")
        canonical = path.with_name(path.stem + "." + uuid.uuid4().hex[:8] + ".native.hwpx")
        builder.save(canonical)
        rendered = path.with_suffix(".rendered.pdf")
        builder.export_pdf(rendered)
        canonical.replace(path)
        builder.close()
        builder = None
        connection.send(("result", {"rendered_pdf": str(rendered), "reopened_in_hangul": True}))
    except Exception as exc:
        connection.send(("error", str(exc)))
    finally:
        if builder is not None:
            builder.close()
        connection.close()


def export_native(output: Path, config: dict) -> dict:
    import win32api

    timeout = float(config.get("timeout_seconds", 120))
    if not 10 <= timeout <= 3600:
        raise ValueError("Hancom timeout_seconds must be between 10 and 3600")
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_export_worker, args=(str(output.resolve()), bool(config.get("visible", False)), send))
    handle = None
    process.start()
    send.close()
    deadline = time.monotonic() + timeout
    completed = False
    try:
        while time.monotonic() < deadline:
            if receive.poll(min(.25, max(0, deadline - time.monotonic()))):
                try:
                    kind, value = receive.recv()
                except EOFError as exc:
                    raise RuntimeError("Hancom validation worker exited without a result") from exc
                if kind == "pid":
                    # Keep the exact process handle; never terminate by a reusable PID or process name.
                    try:
                        handle = win32api.OpenProcess(0x00100001, False, value)
                    except Exception as exc:
                        raise RuntimeError("Cannot obtain the isolated Hancom process handle") from exc
                elif kind == "error":
                    raise RuntimeError(value)
                elif kind == "result":
                    completed = True
                    return value
            elif not process.is_alive():
                raise RuntimeError("Hancom validation worker stopped unexpectedly")
        raise RuntimeError("Hancom validation timed out; a file-access dialog may require approval. The unvalidated HWPX draft was retained.")
    finally:
        if not completed and handle is not None:
            try:
                win32api.TerminateProcess(handle, 1)
            except Exception:
                pass
        process.join(2)
        if process.is_alive():
            process.terminate()
            process.join(5)
        if handle is not None:
            handle.Close()
        receive.close()
