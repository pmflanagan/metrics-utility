"""Render a report definition as an openpyxl workbook."""

import copy

import numpy as np

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from metrics_utility.automation_controller_billing.report.definition import Multiply, Sum


def _reference(ref):
    return f'{get_column_letter(ref.column)}{ref.row}'


def _set_value(cell, value):
    """Preserve native types without inferring formulas or errors from text."""
    if isinstance(value, Multiply):
        cell.value = f'={_reference(value.left)}*{_reference(value.right)}'
        return
    if isinstance(value, Sum):
        cell.value = f'=SUM({_reference(value.start)}:{_reference(value.end)})'
        return
    cell.value = bool(value) if isinstance(value, np.bool_) else value
    # Inspect the bound value too: openpyxl decodes bytes into strings.
    if isinstance(cell.value, str):
        cell.data_type = 's'
    elif cell.data_type == 'f':
        raise TypeError(f'Unsupported report formula: {type(value).__name__}')


def _border_side(side):
    if side is None:
        return None
    return Side(border_style=side.border_style, color=side.color)


def _apply_styles(cell, source, fonts, fills, borders, alignments):
    if source.font is not None:
        if source.font not in fonts:
            fonts[source.font] = Font(name=source.font.name, size=source.font.size, color=source.font.color, bold=source.font.bold)
        cell.font = fonts[source.font]
    if source.fill is not None:
        if source.fill not in fills:
            fills[source.fill] = PatternFill(source.fill.pattern, fgColor=source.fill.fg_color)
        cell.fill = fills[source.fill]
    if source.border is not None:
        if source.border not in borders:
            borders[source.border] = Border(
                left=_border_side(source.border.left),
                right=_border_side(source.border.right),
                top=_border_side(source.border.top),
                bottom=_border_side(source.border.bottom),
            )
        cell.border = borders[source.border]
    if source.alignment is not None:
        if source.alignment not in alignments:
            alignments[source.alignment] = Alignment(horizontal=source.alignment.horizontal, vertical=source.alignment.vertical)
        cell.alignment = alignments[source.alignment]


def _has_presentation(source):
    return (
        source.font is not None
        or source.fill is not None
        or source.border is not None
        or source.alignment is not None
        or source.number_format is not None
    )


def _style_key(cell, source):
    """Identify a resolved cell style independently of openpyxl's tables.

    ``_set_value`` gives date-like values an implicit number format, so the
    already-resolved ``numFmtId`` is part of the key when the definition does
    not name an explicit format.  Otherwise a string cell and a datetime cell
    sharing the same font would collide and lose their distinct formats.
    """
    number_format = source.number_format
    if number_format is None:
        style = getattr(cell, '_style', None)
        number_format = style.numFmtId if style is not None else 0
    return (source.font, source.fill, source.border, source.alignment, number_format)


def _apply_dimensions(ws, sheet):
    for column, dimension in sheet.column_dimensions.items():
        if dimension.width is not None:
            ws.column_dimensions[get_column_letter(column)].width = dimension.width
    for row, dimension in sheet.row_dimensions.items():
        if dimension.height is not None:
            ws.row_dimensions[row].height = dimension.height


def render(definition):
    workbook = Workbook()
    workbook.remove(workbook.active)
    fonts, fills, borders, alignments = {}, {}, {}, {}
    # openpyxl keeps its font/fill/border/alignment/number-format tables on the
    # workbook, so a resolved _style can be reused for every cell in the
    # workbook that shares the same presentation.  Assigning the attributes on
    # every cell hashes each style object on every assignment.
    style_cache = {}
    for sheet in definition.worksheets:
        ws = workbook.create_sheet(sheet.title)
        for start_row, start_column, end_row, end_column in sheet.merges:
            ws.merge_cells(start_row=start_row, start_column=start_column, end_row=end_row, end_column=end_column)
        for source in sheet.cells.values():
            cell = ws.cell(source.row, source.column)
            if source.value is not None:
                _set_value(cell, source.value)
            if not _has_presentation(source):
                continue
            key = _style_key(cell, source)
            cached = style_cache.get(key)
            if cached is not None and hasattr(cell, '_style'):
                # Each cell gets its own StyleArray: openpyxl mutates the array
                # in place when a style is reassigned later.
                cell._style = copy.copy(cached)
                continue
            _apply_styles(cell, source, fonts, fills, borders, alignments)
            if source.number_format is not None:
                cell.number_format = source.number_format
            if hasattr(cell, '_style') and cell._style is not None:
                style_cache[key] = copy.copy(cell._style)
        _apply_dimensions(ws, sheet)
    return workbook
