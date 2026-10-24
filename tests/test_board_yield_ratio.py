"""석고보드 항복비(이선형 근사 꺾임점) 산정 도구 테스트 — 엑셀 원본 의존 없음."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.tools.board_yield_ratio import (
  analyze_workbook,
  board_key_from_sheet,
  check_against_constants,
  fit_bilinear,
  group_mean_ratios,
)
from backend.tools.xlsx_reader import XlsxReadError, column_number, read_workbook


def _bilinear(x: float, xb: float = 2.0, k1: float = 50.0, k2: float = 10.0) -> float:
  return k1 * min(x, xb) + k2 * max(x - xb, 0.0)


def _cell(ref: str, value: float | str | None) -> str:
  if value is None:
    return ""
  if isinstance(value, str):
    return f'<c r="{ref}" t="e"><v>{value}</v></c>'
  return f'<c r="{ref}"><v>{value}</v></c>'


def _write_xlsx(path: Path, sheets: dict[str, list[tuple[float | str | None, float | str | None]]]) -> None:
  """A열 = 하중, D열 = 변위(3행부터)인 최소 xlsx. None은 빈 셀, 문자열은 수식 오류 셀."""
  workbook_sheets = "".join(
    f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>' for index, name in enumerate(sheets, start=1)
  )
  relations = "".join(
    f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
    f'Target="worksheets/sheet{index}.xml"/>'
    for index in range(1, len(sheets) + 1)
  )
  with zipfile.ZipFile(path, "w") as archive:
    archive.writestr(
      "xl/workbook.xml",
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
      f"<sheets>{workbook_sheets}</sheets></workbook>",
    )
    archive.writestr(
      "xl/_rels/workbook.xml.rels",
      f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{relations}</Relationships>',
    )
    for index, rows in enumerate(sheets.values(), start=1):
      body = '<row r="2"><c r="A2" t="inlineStr"><is><t>Load</t></is></c></row>'
      body += "".join(
        f'<row r="{row}">{_cell(f"A{row}", load)}{_cell(f"D{row}", disp)}</row>'
        for row, (load, disp) in enumerate(rows, start=3)
      )
      archive.writestr(
        f"xl/worksheets/sheet{index}.xml",
        f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{body}</sheetData></worksheet>',
      )


class BilinearBreakpointTest(unittest.TestCase):
  def test_recovers_breakpoint_of_exact_bilinear_data(self) -> None:
    x = [0.1 * i for i in range(41)]
    y = [_bilinear(value) for value in x]
    fit = fit_bilinear(x, y)
    self.assertAlmostEqual(fit.breakpoint_x, 2.0, places=9)
    self.assertAlmostEqual(fit.breakpoint_y, 100.0, places=6)
    self.assertAlmostEqual(fit.slope_before, 50.0, places=6)
    self.assertAlmostEqual(fit.slope_after, 10.0, places=6)

  def test_too_few_points_rejected(self) -> None:
    with self.assertRaises(ValueError):
      fit_bilinear([0.0, 1.0, 2.0, 3.0, 4.0, 5.0], [0.0, 1.0, 2.0, 3.0, 4.0, 5.0])

  def test_sheet_name_parsing(self) -> None:
    self.assertEqual(board_key_from_sheet("일반 9.5.0"), ("일반", 9.5))
    self.assertEqual(board_key_from_sheet("방화 12.5-1"), ("방화", 12.5))
    self.assertEqual(board_key_from_sheet("방화 25.0"), ("방화", 25.0))
    self.assertEqual(board_key_from_sheet("방화 15.3"), ("방화", 15.0))
    self.assertEqual(board_key_from_sheet("고강도 12.5.4"), ("고강도일반", 12.5))
    with self.assertRaises(ValueError):
      board_key_from_sheet("정리표")

  def test_column_number(self) -> None:
    self.assertEqual(column_number("A"), 1)
    self.assertEqual(column_number("Q"), 17)
    self.assertEqual(column_number("AD"), 30)


class WorkbookAnalysisTest(unittest.TestCase):
  def test_workbook_ratio_uses_points_up_to_peak_load(self) -> None:
    rising = [(_bilinear(0.1 * i), 0.1 * i) for i in range(41)]  # Pu = 120 (x = 4.0)
    falling = [(110.0, 4.5), (90.0, 5.0)]  # 최대하중 이후 — 근사에서 제외
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "flexure.xlsx"
      _write_xlsx(path, {"일반 9.5.0": rising + falling, "일반 9.5.1": rising, "CHART-일반": [(1.0, 1.0)]})
      self.assertEqual(sorted(read_workbook(path)), ["CHART-일반", "일반 9.5.0", "일반 9.5.1"])
      results = analyze_workbook(path)
    self.assertEqual([result.sheet for result in results], ["일반 9.5.0", "일반 9.5.1"])
    for result in results:
      self.assertAlmostEqual(result.ultimate_load, 120.0)
      self.assertAlmostEqual(result.ratio, 100.0 / 120.0, places=6)
    groups = group_mean_ratios(results)
    problems = check_against_constants(groups)
    self.assertTrue(any("('일반', 9.5): 산정 0.83" in problem for problem in problems))
    self.assertTrue(any("엑셀에 시험체가 없습니다" in problem for problem in problems))

  def test_mid_series_error_or_missing_cell_rejected(self) -> None:
    # 중간 수식 오류·결측을 자료 끝으로 보고 잘린 자료로 산정하지 않는다
    rising = [(_bilinear(0.1 * i), 0.1 * i) for i in range(41)]
    broken_rows = {
      "error": rising[:10] + [("#DIV/0!", 1.0)] + rising[11:],
      "missing": rising[:10] + [(None, 1.0)] + rising[11:],
    }
    for label, rows in broken_rows.items():
      with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "flexure.xlsx"
        _write_xlsx(path, {"일반 9.5.0": rows})
        with self.assertRaisesRegex(XlsxReadError, "13행"):
          analyze_workbook(path)


if __name__ == "__main__":
  unittest.main()
