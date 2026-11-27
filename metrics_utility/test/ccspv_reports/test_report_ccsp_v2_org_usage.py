"""Unit tests for the CCSPv2 per-organization report sheets.

Covers the grouped implementations of ``_build_data_section_usage_by_org`` and
``_add_organization_sheets``, including indirect-node counts, categorical
organization names, null organization names, and input-frame immutability.
"""

import numpy as np
import pandas as pd
import pytest

from metrics_utility.automation_controller_billing.report.report_ccsp_v2 import ReportCCSPv2
from metrics_utility.metric_utils import DIRECT, INDIRECT


BASE_EXTRA_PARAMS = {
    'price_per_node': 50.0,
    'report_period': '2025-07',
    'report_sku': 'TEST-SKU',
    'report_h1_heading': 'Test Report',
    'report_po_number': 'PO-123',
    'report_company_name': 'Test Company',
    'report_email': 'test@example.com',
    'report_rhn_login': 'testuser',
    'report_sku_description': 'Test SKU Description',
    'report_organization_filter': None,
}


def _report(optional_sheets=None):
    return ReportCCSPv2(dataframes={}, extra_params=dict(BASE_EXTRA_PARAMS, optional_sheets=optional_sheets))


def _worksheet(report, title='TestSheet'):
    report.wb.create_sheet(title=title)
    return report.wb.worksheets[-1]


def _jhs_frame():
    return pd.DataFrame(
        {
            'organization_name': ['Org B', 'Org A', 'Org B', 'Org B', 'Org A'],
            'managed_node_type': [DIRECT, DIRECT, INDIRECT, DIRECT, INDIRECT],
            'host_name': ['b1', 'a1', 'b-ind', 'b1', 'a-ind'],
            'task_runs': [1, 2, 4, 8, 16],
            'job_remote_id': ['j1', 'j2', 'j3', 'j4', 'j3'],
            'install_uuid': ['u', 'u', 'u', 'u', 'u'],
            'first_automation': pd.to_datetime(['2025-07-01'] * 5),
            'last_automation': pd.to_datetime(['2025-07-02'] * 5),
        }
    )


def _read_table(ws, ncols, end_row):
    return [tuple(ws.cell(row=row, column=column).value for column in range(1, ncols + 1)) for row in range(1, end_row)]


def test_usage_by_org_direct_counts_and_organizations():
    r = _report(optional_sheets=[])
    ws = _worksheet(r)
    df = _jhs_frame()

    end_row = r._build_data_section_usage_by_org(1, ws, df)

    assert _read_table(ws, 5, end_row) == [
        ('Organization name', 'Job runs', 'Unique managed nodes\nautomated', 'Non-unique managed\nnodes automated', 'Number of task\nruns'),
        # Org A: one direct host (a1); the indirect a-ind row is excluded.
        ('Org A', 2, 1, 1, 18),
        # Org B: b1 counted twice (non-unique) but once unique; j3 shared by 2 rows.
        ('Org B', 3, 1, 2, 13),
    ]


def test_usage_by_org_includes_indirect_counts_when_enabled():
    r = _report(optional_sheets=['indirectly_managed_nodes'])
    ws = _worksheet(r)
    df = _jhs_frame()

    end_row = r._build_data_section_usage_by_org(1, ws, df)

    assert _read_table(ws, 7, end_row) == [
        (
            'Organization name',
            'Job runs',
            'Unique managed nodes\nautomated',
            'Non-unique managed\nnodes automated',
            'Unique indirect managed nodes\nautomated',
            'Non-unique indirect managed\nnodes automated',
            'Number of task\nruns',
        ),
        ('Org A', 2, 1, 1, 1, 1, 18),
        ('Org B', 3, 1, 2, 1, 1, 13),
    ]


def test_usage_by_org_does_not_mutate_input_frame():
    r = _report(optional_sheets=[])
    ws = _worksheet(r)
    df = _jhs_frame()
    original = df.copy()

    r._build_data_section_usage_by_org(1, ws, df)

    pd.testing.assert_frame_equal(df, original)
    assert 'job_remote_id_install_uuid' not in df.columns


def test_usage_by_org_keeps_nan_organization_names():
    """The grouped implementation still emits the dropna=False NaN group last."""
    r = _report(optional_sheets=[])
    ws = _worksheet(r)
    df = _jhs_frame()
    df.loc[0, 'organization_name'] = None

    end_row = r._build_data_section_usage_by_org(1, ws, df)
    rows = _read_table(ws, 5, end_row)

    assert len(rows) == 4  # header + Org A + Org B + NaN group
    assert rows[1][0] == 'Org A'
    assert rows[2][0] == 'Org B'
    assert pd.isna(rows[3][0])
    assert rows[3][1:] == (1, 1, 1, 1)


def _org_frame(categories=None):
    data = {
        'organization_name': ['Org B', 'Org A', 'Org B'],
        'managed_node_type': [DIRECT, DIRECT, DIRECT],
        'host_name': ['b1', 'a1', 'b2'],
        'task_runs': [1, 2, 4],
        'first_automation': pd.to_datetime(['2025-07-01'] * 3),
        'last_automation': pd.to_datetime(['2025-07-02'] * 3),
    }
    if categories is not None:
        data['organization_name'] = pd.Categorical(data['organization_name'], categories=categories)
    return pd.DataFrame(data)


@pytest.mark.parametrize(
    'frame_factory',
    [
        lambda: _org_frame(),
        lambda: _org_frame(categories=['Org A', 'Org B', 'Org C']),
        # Category order deliberately differs from alphabetical order.
        lambda: _org_frame(categories=['Org B', 'Org A', 'Org C']),
    ],
    ids=['object', 'categorical-with-unobserved', 'categorical-unsorted'],
)
def test_add_organization_sheets_order_and_content(frame_factory):
    r = _report(optional_sheets=['managed_nodes_by_organizations'])
    r.wb.remove(r.wb.active)
    df = frame_factory()

    end_sheet_index = r._add_organization_sheets(0, df)

    # One sheet per observed organization, in sorted order (Org C is unobserved).
    assert [ws.title for ws in r.wb.worksheets] == ['Org A', 'Org B']
    assert end_sheet_index == 2

    org_a = _read_table(r.wb.worksheets[0], 5, 3)
    org_b = _read_table(r.wb.worksheets[1], 5, 4)
    assert org_a == [
        ('Host name', 'Job runs', 'Number of task\nruns', 'First\nautomation', 'Last\nautomation'),
        ('a1', 1, 2, pd.Timestamp('2025-07-01'), pd.Timestamp('2025-07-02')),
    ]
    assert [row[0] for row in org_b[1:]] == ['b1', 'b2']


@pytest.mark.parametrize('missing_organization', [None, np.nan], ids=['none', 'nan'])
def test_add_organization_sheets_handles_null_organization_names(missing_organization):
    """A null organization must not break sorting or sheet creation; its group goes last."""
    r = _report(optional_sheets=['managed_nodes_by_organizations'])
    r.wb.remove(r.wb.active)
    df = _org_frame()
    # Group order becomes Org B, Org A, <null>: the sheets must still be sorted.
    df.loc[2, 'organization_name'] = missing_organization
    original = df.copy()

    end_sheet_index = r._add_organization_sheets(0, df)

    assert [ws.title for ws in r.wb.worksheets] == ['Org A', 'Org B', 'No organization name']
    assert end_sheet_index == 3
    # The null group is labelled with the same placeholder the dataframe engine uses;
    # the placeholder fits in a sheet title, so no separate heading row is needed.
    assert _read_table(r.wb.worksheets[2], 5, 3) == [
        ('Host name', 'Job runs', 'Number of task\nruns', 'First\nautomation', 'Last\nautomation'),
        ('b2', 1, 4, pd.Timestamp('2025-07-01'), pd.Timestamp('2025-07-02')),
    ]
    pd.testing.assert_frame_equal(df, original)


def test_add_organization_sheets_does_not_mutate_input_frame():
    r = _report(optional_sheets=['managed_nodes_by_organizations'])
    r.wb.remove(r.wb.active)
    df = _org_frame(categories=['Org A', 'Org B', 'Org C'])
    original = df.copy()

    r._add_organization_sheets(0, df)

    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize(
    'frame_factory',
    [
        lambda: _org_frame(),
        lambda: _org_frame(categories=['Org A', 'Org B', 'Org C']),
        # Category order deliberately differs from alphabetical order.
        lambda: _org_frame(categories=['Org B', 'Org A', 'Org C']),
    ],
    ids=['object', 'categorical-with-unobserved', 'categorical-unsorted'],
)
def test_add_organization_sheets_matches_explicit_boolean_filtering(frame_factory):
    """Each sheet must hold the same rows as the previous '== organization' filter."""
    df = frame_factory()
    r = _report(optional_sheets=['managed_nodes_by_organizations'])
    r.wb.remove(r.wb.active)

    r._add_organization_sheets(0, df)

    for index, organization_name in enumerate(sorted(df['organization_name'].unique(), key=str)):
        expected = _report(optional_sheets=['managed_nodes_by_organizations'])
        expected.wb.remove(expected.wb.active)
        ws = expected.wb.create_sheet(title=organization_name)
        filtered = df[df['organization_name'] == organization_name]
        end_row = expected._build_data_section_usage_by_node(1, ws, filtered, mode='by_organization')

        actual_ws = r.wb.worksheets[index]
        assert _read_table(actual_ws, 5, end_row) == _read_table(ws, 5, end_row)
