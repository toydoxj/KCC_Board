"""표준 라이브러리 xlsx 읽기 — 산정 도구(시험 원자료) 전용.

셀 값과 수식의 캐시값만 읽는다(수식 재계산 없음). 외부 의존성(openpyxl 등)을 추가하지 않기 위해 둔다.
계산엔진에서는 호출하지 않는다.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_NS = {"m": _MAIN_NS}
_CELL_REF = re.compile(r"^([A-Z]+)([0-9]+)$")

CellValue = float | str | bool
# 시트 이름 → {(행, 열): 값}, 행·열은 1부터
Sheet = dict[tuple[int, int], CellValue]


class XlsxReadError(ValueError):
  """xlsx 구조를 해석할 수 없을 때."""


def column_number(letters: str) -> int:
  """열 문자(A, B, …, AA) → 1부터 시작하는 열 번호."""
  number = 0
  for char in letters:
    if not "A" <= char <= "Z":
      raise XlsxReadError(f"열 문자가 아닙니다: {letters!r}")
    number = number * 26 + ord(char) - 64
  return number


def _cell_position(ref: str) -> tuple[int, int]:
  match = _CELL_REF.match(ref)
  if match is None:
    raise XlsxReadError(f"셀 참조를 해석할 수 없습니다: {ref!r}")
  return int(match.group(2)), column_number(match.group(1))


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
  if "xl/sharedStrings.xml" not in archive.namelist():
    return []
  root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
  return ["".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")) for item in root.findall("m:si", _NS)]


def _sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
  workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
  relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
  targets = {relation.get("Id"): relation.get("Target") or "" for relation in relations}
  sheets = workbook.find("m:sheets", _NS)
  if sheets is None:
    raise XlsxReadError("workbook.xml에 sheets가 없습니다.")
  paths: list[tuple[str, str]] = []
  for sheet in sheets:
    target = targets.get(sheet.get(_REL_ID))
    if not target:
      raise XlsxReadError(f"시트 경로를 찾을 수 없습니다: {sheet.get('name')!r}")
    path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
    paths.append((str(sheet.get("name")), path))
  return paths


def _cell_value(cell: ElementTree.Element, shared: list[str]) -> CellValue | None:
  value_node = cell.find("m:v", _NS)
  cell_type = cell.get("t")
  if cell_type == "inlineStr":
    return "".join(node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t"))
  if value_node is None or value_node.text is None:
    return None
  text = value_node.text
  if cell_type == "s":
    return shared[int(text)]
  if cell_type in ("str", "e"):
    return text
  if cell_type == "b":
    return text == "1"
  return float(text)


def read_workbook(path: Path, include: Callable[[str], bool] | None = None) -> dict[str, Sheet]:
  """xlsx의 시트별 셀 값을 읽는다. include가 주어지면 True인 시트만 읽는다."""
  with zipfile.ZipFile(path) as archive:
    shared = _shared_strings(archive)
    workbook: dict[str, Sheet] = {}
    for name, sheet_path in _sheet_paths(archive):
      if include is not None and not include(name):
        continue
      cells: Sheet = {}
      with archive.open(sheet_path) as stream:
        for _, element in ElementTree.iterparse(stream):
          if element.tag == f"{{{_MAIN_NS}}}c":
            value = _cell_value(element, shared)
            if value is not None:
              cells[_cell_position(str(element.get("r")))] = value
            element.clear()
      workbook[name] = cells
  return workbook


def column_letters(number: int) -> str:
  """1부터 시작하는 열 번호 → 열 문자."""
  letters = ""
  while number:
    number, remainder = divmod(number - 1, 26)
    letters = chr(65 + remainder) + letters
  return letters


def numeric_column_pairs(sheet: Sheet, first_row: int, x_column: int, y_column: int) -> list[tuple[float, float]]:
  """first_row부터 두 열이 모두 숫자인 연속 행의 (x, y) 목록.

  두 셀이 모두 빈 행을 자료 끝으로 본다. 한쪽만 비었거나 숫자가 아닌 값(수식 오류 등)이 있으면
  잘린 자료로 산정하지 않도록 셀 위치와 함께 예외를 발생시킨다.
  """
  pairs: list[tuple[float, float]] = []
  row = first_row
  while True:
    x_value = sheet.get((row, x_column))
    y_value = sheet.get((row, y_column))
    if x_value is None and y_value is None:
      return pairs
    if not isinstance(x_value, float) or not isinstance(y_value, float):
      raise XlsxReadError(
        f"{row}행 자료가 숫자가 아닙니다: {column_letters(x_column)}{row}={x_value!r}, "
        f"{column_letters(y_column)}{row}={y_value!r}"
      )
    pairs.append((x_value, y_value))
    row += 1
