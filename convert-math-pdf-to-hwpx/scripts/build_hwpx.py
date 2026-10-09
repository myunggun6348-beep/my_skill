from __future__ import annotations

from pathlib import Path


class HangulBuilder:
    def __init__(self, visible: bool = False):
        if __import__("platform").system() != "Windows":
            raise RuntimeError("Hangul COM generation requires Windows")
        try:
            import win32com.client
        except ImportError as exc:
            raise RuntimeError("pywin32 is required. Install requirements.txt.") from exc
        self.hwp = win32com.client.DispatchEx("HWPFrame.HwpObject")
        self.hwp.XHwpWindows.Item(0).Visible = bool(visible)
        self.security_module_registered = bool(self.hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule"))
        if not self.security_module_registered:
            self.hwp.XHwpWindows.Item(0).Visible = True
            print("Hancom may request file access approval for this conversion. Approve only the requested task files.", flush=True)
        try:
            if self.hwp.XHwpDocuments.Count == 0:
                self.hwp.XHwpDocuments.Add(True)
        except Exception:
            # Some Hangul versions create a blank document during Dispatch.
            pass

    def insert_text(self, text: str) -> None:
        param = self.hwp.HParameterSet.HInsertText
        self.hwp.HAction.GetDefault("InsertText", param.HSet)
        param.Text = text
        if not self.hwp.HAction.Execute("InsertText", param.HSet):
            raise RuntimeError("Hangul text insertion failed")

    def paragraph(self) -> None:
        self.hwp.HAction.Run("BreakPara")

    def page_break(self) -> None:
        self.hwp.HAction.Run("BreakPage")

    def insert_equation(self, command: str, font_size_pt: float = 10) -> None:
        eq = self.hwp.HParameterSet.HEqEdit
        self.hwp.HAction.GetDefault("EquationCreate", eq.HSet)
        eq.String = command
        eq.BaseUnit = round(font_size_pt * 100)
        eq.EqFontName = "HYhwpEQ"
        if not self.hwp.HAction.Execute("EquationCreate", eq.HSet):
            raise RuntimeError(f"Hangul rejected equation command: {command}")

    def insert_image(self, path: Path) -> None:
        from PIL import Image
        with Image.open(path) as image:
            width = min(140.0, 230.0 * image.width / image.height)
            height = width * image.height / image.width
        control = self.hwp.InsertPicture(str(path.resolve()), True, 1, False, False, 0, width, height)
        if not control:
            raise RuntimeError(f"Hangul failed to insert image: {path}")
        properties = control.Properties
        properties.SetItem("TreatAsChar", True)
        control.Properties = properties

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if not self.hwp.SaveAs(str(output.resolve()), "HWPX", ""):
            raise RuntimeError(f"Hangul failed to save HWPX: {output}")

    def export_pdf(self, output: Path) -> None:
        if not self.hwp.SaveAs(str(output.resolve()), "PDF", ""):
            raise RuntimeError(f"Hangul failed to export PDF: {output}")

    def close(self) -> None:
        try:
            self.hwp.Clear(1)
        except Exception:
            pass
        finally:
            try:
                self.hwp.Quit()
            except Exception:
                pass


def build_hwpx(analysis: dict, output: Path, config: dict) -> dict:
    if analysis.get("mode") == "fidelity":
        from preserve_layout import build_fidelity
        return build_fidelity(analysis, output, config)
    from validate_output import equation_issues
    issues = equation_issues(analysis, config)
    if issues:
        raise ValueError("Native equation reconstruction is incomplete: " + "; ".join(issues))
    builder = HangulBuilder(visible=bool(config.get("hwp", {}).get("visible", False)))
    inserted = {"text": 0, "equation": 0, "image": 0, "review": 0}
    try:
        for page_index, page in enumerate(analysis["pages"]):
            for element in page["elements"]:
                kind = element["kind"]
                if kind == "equation" and element.get("hwp_command"):
                    builder.insert_equation(element["hwp_command"])
                    inserted["equation"] += 1
                elif kind == "image" or (kind == "review" and element.get("asset")):
                    builder.insert_image(Path(element["asset"]))
                    inserted["image"] += 1
                    inserted["review"] += int(kind == "review")
                else:
                    builder.insert_text(element.get("text", ""))
                    inserted["text"] += 1
                    inserted["review"] += int(kind == "review")
                builder.paragraph()
            if page_index + 1 < len(analysis["pages"]):
                builder.page_break()
        builder.save(output)
        pdf_output = output.with_suffix(".rendered.pdf")
        if config.get("validation", {}).get("require_pdf_export", True):
            builder.export_pdf(pdf_output)
        return {"inserted": inserted, "rendered_pdf": str(pdf_output) if pdf_output.exists() else ""}
    finally:
        builder.close()
