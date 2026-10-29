"""Worksheet naming tests backported from the upstream change."""

import pandas as pd

from metrics_utility.automation_controller_billing.report.base import Base


class ConcreteReport(Base):
    """Instantiable subclass for testing Base helpers."""

    def __init__(self, extra_params=None):
        from openpyxl import Workbook

        self.wb = Workbook()
        self.extra_params = extra_params or {}
        self.dataframes = {}


def _report(dedup=False):
    deduplicator = 'ccsp-experimental' if dedup else None
    return ConcreteReport(extra_params={'deduplicator': deduplicator, 'optional_sheets': None})


class TestSafeSheetTitle:
    """Tests for Base._safe_sheet_title truncation and deduplication."""

    def test_short_title_unchanged(self):
        """Titles within the 31-char limit are returned as-is."""
        assert Base._safe_sheet_title('ShortName') == 'ShortName'

    def test_exactly_31_chars_unchanged(self):
        """A title exactly at the limit is not modified."""
        title = 'a' * 31
        assert Base._safe_sheet_title(title) == title

    def test_title_over_31_chars_truncated(self):
        """Titles exceeding 31 characters are truncated."""
        title = 'a' * 40
        result = Base._safe_sheet_title(title)
        assert len(result) == 31
        assert result == 'a' * 31

    def test_truncation_does_not_collide_with_existing(self):
        """When truncation causes a collision, a ~N suffix is appended."""
        long_name_1 = 'cba-v-np-101005454-iac-tst-vmpprdtst1'
        long_name_2 = 'cba-v-np-101005454-iac-tst-vmpprdtst2'
        first = Base._safe_sheet_title(long_name_1)
        second = Base._safe_sheet_title(long_name_2, existing_titles={first})
        assert first != second
        assert len(second) <= 31
        assert second.endswith('~2')

    def test_multiple_collisions_increment_suffix(self):
        """Successive collisions produce ~2, ~3, ~4 etc., all unique."""
        base = 'x' * 35
        existing = set()
        titles = []
        for _ in range(5):
            t = Base._safe_sheet_title(base, existing)
            assert len(t) <= 31
            assert t not in existing
            existing.add(t)
            titles.append(t)
        assert len(set(titles)) == 5

    def test_empty_string_unchanged(self):
        """Empty string is returned as-is (no crash)."""
        assert Base._safe_sheet_title('') == ''

    def test_no_existing_titles_short_circuit(self):
        """Without existing titles, a long name is simply truncated."""
        title = 'z' * 50
        result = Base._safe_sheet_title(title)
        assert len(result) == 31

    def test_real_world_org_name_37_chars(self):
        """Real customer org name (37 chars) truncates to 31."""
        org_name = 'cba-v-np-101005454-iac-tst-vmpprdtst1'
        assert len(org_name) == 37
        result = Base._safe_sheet_title(org_name)
        assert len(result) == 31
        assert result == 'cba-v-np-101005454-iac-tst-vmpp'

    def test_case_insensitive_collision(self):
        """Excel treats sheet names as case-insensitive, so 'ABC' and 'abc'
        collide.  _safe_sheet_title must disambiguate them."""
        long_upper = 'A' * 35
        long_lower = 'a' * 35
        first = Base._safe_sheet_title(long_upper)
        second = Base._safe_sheet_title(long_lower, existing_titles={first})
        assert first.lower() != second.lower()
        assert len(second) <= 31
        assert second.endswith('~2')

    def test_invalid_chars_replaced(self):
        """Characters forbidden by Excel (\\*?:/[]) are replaced with _."""
        title = 'org:name/with*bad[chars]?here\\now'
        result = Base._safe_sheet_title(title)
        for ch in (':', '/', '*', '[', ']', '?', '\\'):
            assert ch not in result
        assert result == 'org_name_with_bad_chars__here_n'

    def test_invalid_chars_with_short_title(self):
        """Short title with invalid chars is sanitized without truncation."""
        result = Base._safe_sheet_title('a:b/c*d')
        assert result == 'a_b_c_d'
        assert len(result) == 7

    def test_invalid_chars_collision_after_sanitization(self):
        """Two titles that differ only in invalid chars collide after
        sanitization and get disambiguated."""
        first = Base._safe_sheet_title('org:name')
        second = Base._safe_sheet_title('org/name', existing_titles={first})
        assert first != second
        assert second.endswith('~2')

    def test_leading_apostrophe_replaced(self):
        """A title starting with ' gets the apostrophe replaced."""
        result = Base._safe_sheet_title("'Acme Corp'")
        assert not result.startswith("'")
        assert not result.endswith("'")
        assert result == '_Acme Corp_'

    def test_trailing_apostrophe_from_truncation(self):
        """If truncation leaves a trailing ', it is replaced."""
        # 30 chars + apostrophe at position 31 after truncation
        title = 'a' * 30 + "'" + 'bbb'
        result = Base._safe_sheet_title(title)
        assert len(result) <= 31
        assert not result.endswith("'")

    def test_reserved_name_history(self):
        """The reserved name 'History' (case-insensitive) is renamed."""
        for name in ('History', 'history', 'HISTORY'):
            result = Base._safe_sheet_title(name)
            assert result.lower() != 'history'

    def test_history_with_suffix_not_reserved(self):
        """'History_dept' is not the reserved name and passes through."""
        result = Base._safe_sheet_title('History_dept')
        assert result == 'History_dept'


class TestAddSheet:
    def test_long_title_truncated_to_31(self):
        """add_sheet truncates titles exceeding 31 characters."""
        r = _report()
        long_name = 'cba-v-np-101005454-iac-tst-vmpprdtst1'
        ws = r.add_sheet(long_name, 1)
        assert len(ws.title) <= 31

    def test_two_long_colliding_names_disambiguated(self):
        """Two long names sharing a 31-char prefix get distinct tab titles."""
        r = _report()
        r.wb.remove(r.wb.active)
        name_a = 'cba-v-np-101005454-iac-tst-vmpprdtst1'
        name_b = 'cba-v-np-101005454-iac-tst-vmpprdtst2'
        ws_a = r.add_sheet(name_a, 0)
        ws_b = r.add_sheet(name_b, 1)
        assert ws_a.title != ws_b.title
        assert len(ws_a.title) <= 31
        assert len(ws_b.title) <= 31


def _ccspv2_extra_params(optional_sheets):
    """Minimal extra_params for a CCSPv2 report."""
    return {
        'price_per_node': 11.55,
        'report_period': '2024-02',
        'report_sku': 'MCT3752MO',
        'report_h1_heading': 'CCSP NA Direct Reporting Template',
        'report_po_number': '123',
        'report_company_name': 'Partner A',
        'report_email': 'email@email.com',
        'report_rhn_login': 'test_login',
        'report_sku_description': 'Test SKU',
        'report_end_user_company_name': 'Customer A',
        'report_end_user_company_city': 'Springfield',
        'report_end_user_company_state': 'TX',
        'report_end_user_company_country': 'US',
        'report_organization_filter': None,
        'opt_since': None,
        'opt_until': None,
        'month_since': None,
        'month_until': None,
        'optional_sheets': optional_sheets,
        'deduplicator': None,
    }


def _jhs_df_with_org(org_name):
    """Minimal job_host_summary dataframe with a single organization."""
    return pd.DataFrame(
        {
            'host_name': ['host1'],
            'organization_name': [org_name],
            'managed_node_type': [1],
            'task_runs': [5],
            'first_automation': ['2024-01-01'],
            'last_automation': ['2024-01-02'],
            'job_remote_id': ['j1'],
            'install_uuid': ['u1'],
            'original_host_name': ['host1'],
            'job_template_name': ['tmpl1'],
            'job_created': ['2024-01-01'],
            'managed_node_types_set': [['direct']],
            'events': [['ev1']],
            'canonical_facts': [{}],
            'facts': [{}],
        }
    )


class TestCCSPv2LongOrgNameHeader:
    """Test that CCSPv2 build_spreadsheet writes a full org name header
    when the organization name is truncated."""

    def test_truncated_org_gets_header_row(self):
        from metrics_utility.automation_controller_billing.report.report_ccsp_v2 import ReportCCSPv2

        long_org = 'cba-v-np-101005454-iac-tst-vmpprdtst1'
        assert len(long_org) > 31
        sheets = ['managed_nodes_by_organizations']
        dataframes = {
            'job_host_summary': _jhs_df_with_org(long_org),
            'main_jobevent': None,
            'main_host': pd.DataFrame(),
            'data_collection_status': pd.DataFrame(),
        }
        report = ReportCCSPv2(dataframes, _ccspv2_extra_params(sheets))
        wb = report.build_spreadsheet()

        ws = wb.worksheets[0]
        assert len(ws.title) <= 31
        assert ws.cell(row=1, column=1).value == long_org
        assert ws.cell(row=1, column=1).font.bold is True
        assert ws.cell(row=1, column=1).data_type == 's'
        assert ws.cell(row=2, column=1).value is not None

    def test_short_org_no_header_row(self):
        from metrics_utility.automation_controller_billing.report.report_ccsp_v2 import ReportCCSPv2

        short_org = 'ShortOrg'
        sheets = ['managed_nodes_by_organizations']
        dataframes = {
            'job_host_summary': _jhs_df_with_org(short_org),
            'main_jobevent': None,
            'main_host': pd.DataFrame(),
            'data_collection_status': pd.DataFrame(),
        }
        report = ReportCCSPv2(dataframes, _ccspv2_extra_params(sheets))
        wb = report.build_spreadsheet()

        ws = wb.worksheets[0]
        assert ws.title == short_org
        assert ws.cell(row=1, column=1).value != short_org

    def test_formula_injection_prevented(self):
        """Org names starting with '=' must not be evaluated as formulas."""
        from metrics_utility.automation_controller_billing.report.report_ccsp_v2 import ReportCCSPv2

        evil_org = '=CMD-injection-padding-to-exceed-31-chars'
        assert len(evil_org) > 31
        sheets = ['managed_nodes_by_organizations']
        dataframes = {
            'job_host_summary': _jhs_df_with_org(evil_org),
            'main_jobevent': None,
            'main_host': pd.DataFrame(),
            'data_collection_status': pd.DataFrame(),
        }
        report = ReportCCSPv2(dataframes, _ccspv2_extra_params(sheets))
        wb = report.build_spreadsheet()

        ws = wb.worksheets[0]
        assert ws.cell(row=1, column=1).data_type == 's'
        assert ws.cell(row=1, column=1).value == evil_org
