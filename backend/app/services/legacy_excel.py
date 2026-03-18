from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol


class LegacyExcelConversionError(Exception):
    """Raised when a legacy Excel workbook cannot be converted safely."""


class SupportsLegacyExcelConverter(Protocol):
    def convert_xls_to_xlsx(self, *, source_path: Path, output_path: Path) -> None:
        """Convert a legacy .xls workbook into .xlsx using an external runtime."""

    def convert_xlsx_to_xls(self, *, source_path: Path, output_path: Path) -> None:
        """Convert a .xlsx workbook back into legacy .xls format."""


class ExcelComLegacyConverter:
    _XLS_FILE_FORMAT = 56
    _XLSX_FILE_FORMAT = 51

    def convert_xls_to_xlsx(self, *, source_path: Path, output_path: Path) -> None:
        self._convert(source_path=source_path, output_path=output_path, file_format=self._XLSX_FILE_FORMAT)

    def convert_xlsx_to_xls(self, *, source_path: Path, output_path: Path) -> None:
        self._convert(source_path=source_path, output_path=output_path, file_format=self._XLS_FILE_FORMAT)

    def _convert(self, *, source_path: Path, output_path: Path, file_format: int) -> None:
        if sys.platform != "win32":
            raise LegacyExcelConversionError(
                "Legacy .xls translation requires Microsoft Excel automation on Windows."
            )
        resolved_source = source_path.resolve()
        resolved_output = output_path.resolve()
        if not resolved_source.exists():
            raise LegacyExcelConversionError(
                f"Legacy Excel source workbook was not found: {resolved_source}"
            )
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        if resolved_output.exists():
            resolved_output.unlink()

        script_path = self._write_vbscript()
        try:
            completed = subprocess.run(
                [
                    "cscript.exe",
                    "//NoLogo",
                    str(script_path),
                    str(resolved_source),
                    str(resolved_output),
                    str(file_format),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError as exc:
            raise LegacyExcelConversionError(
                "Legacy .xls translation requires Windows Script Host and Microsoft Excel."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise LegacyExcelConversionError(
                "Microsoft Excel timed out while converting the legacy workbook."
            ) from exc
        finally:
            script_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            error_output = completed.stderr.strip() or completed.stdout.strip()
            if not error_output:
                error_output = "Microsoft Excel could not convert the legacy workbook."
            raise LegacyExcelConversionError(error_output)
        if not resolved_output.exists():
            raise LegacyExcelConversionError(
                "Microsoft Excel reported success but no converted workbook was created."
            )

    def _write_vbscript(self) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".vbs",
            delete=False,
        ) as handle:
            handle.write(_VBSCRIPT)
            return Path(handle.name)


_VBSCRIPT = """Option Explicit

Sub Fail(message, code)
  WScript.StdErr.WriteLine message
  WScript.Quit code
End Sub

Dim sourcePath
Dim outputPath
Dim fileFormat
Dim excelApp
Dim workbook
Dim fso

If WScript.Arguments.Count <> 3 Then
  Fail "Expected source workbook, output workbook, and Excel file format.", 64
End If

sourcePath = WScript.Arguments(0)
outputPath = WScript.Arguments(1)
fileFormat = CInt(WScript.Arguments(2))

Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(sourcePath) Then
  Fail "Source workbook was not found: " & sourcePath, 66
End If

On Error Resume Next
Set excelApp = CreateObject("Excel.Application")
If Err.Number <> 0 Then
  Fail "Microsoft Excel automation is unavailable: " & Err.Description, 70
End If

Err.Clear
excelApp.DisplayAlerts = False
excelApp.Visible = False
Set workbook = excelApp.Workbooks.Open(sourcePath, False, False)
If Err.Number <> 0 Then
  excelApp.Quit
  Fail "Microsoft Excel could not open workbook: " & Err.Description, 71
End If

If fso.FileExists(outputPath) Then
  fso.DeleteFile outputPath, True
End If

Err.Clear
workbook.SaveAs outputPath, fileFormat
If Err.Number <> 0 Then
  workbook.Close False
  excelApp.Quit
  Fail "Microsoft Excel could not save workbook: " & Err.Description, 72
End If

workbook.Close False
excelApp.Quit

If Not fso.FileExists(outputPath) Then
  Fail "Microsoft Excel did not create the converted workbook.", 73
End If

WScript.Quit 0
"""
