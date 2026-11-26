"""Unit tests for DataframeContentUsage static regex helper methods."""

import pandas as pd

from metrics_utility.automation_controller_billing.dataframe_engine.dataframe_content_usage import (
    DataframeContentUsage,
    _extract_collection_name_cached,
    _extract_role_name_cached,
)


# ---------------------------------------------------------------------------
# extract_collection_name
# ---------------------------------------------------------------------------


class TestExtractCollectionName:
    def test_fully_qualified_collection_module(self):
        """namespace.collection.module_name -> namespace.collection"""
        assert DataframeContentUsage.extract_collection_name('ansible.builtin.copy') == 'ansible.builtin'

    def test_four_part_fqcn(self):
        """namespace.collection.role.task -> namespace.collection"""
        assert DataframeContentUsage.extract_collection_name('community.general.git_config.subtask') == 'community.general'

    def test_two_part_name_returns_none(self):
        """namespace.collection (no third segment) -> None"""
        assert DataframeContentUsage.extract_collection_name('my_namespace.my_collection') is None

    def test_bare_module_name_returns_none(self):
        """plain module name like 'copy' -> None"""
        assert DataframeContentUsage.extract_collection_name('copy') is None

    def test_none_input_returns_none(self):
        assert DataframeContentUsage.extract_collection_name(None) is None

    def test_empty_string_returns_none(self):
        assert DataframeContentUsage.extract_collection_name('') is None

    def test_redhat_namespace(self):
        assert DataframeContentUsage.extract_collection_name('redhat.rhel_system_roles.selinux') == 'redhat.rhel_system_roles'

    def test_numeric_segments_not_matched(self):
        """Names containing numbers in the right places should still match."""
        assert DataframeContentUsage.extract_collection_name('acme.col1.task') == 'acme.col1'

    def test_invalid_characters_returns_none(self):
        """Non-word characters (spaces, dashes, slashes) break the match."""
        assert DataframeContentUsage.extract_collection_name('ansible.builtin.copy-more') is None
        assert DataframeContentUsage.extract_collection_name('ansible builtin.copy') is None
        assert DataframeContentUsage.extract_collection_name('ns/col/mod') is None

    def test_nan_returns_none(self):
        assert DataframeContentUsage.extract_collection_name(float('nan')) is None

    def test_unhashable_inputs_return_none(self):
        """Guard must run before the lru_cache so unhashable values never reach it."""
        assert DataframeContentUsage.extract_collection_name([]) is None
        assert DataframeContentUsage.extract_collection_name({}) is None
        assert DataframeContentUsage.extract_collection_name(['a.b.c']) is None
        assert DataframeContentUsage.extract_collection_name({'a': 'b'}) is None

    def test_non_string_inputs_return_none(self):
        assert DataframeContentUsage.extract_collection_name(42) is None
        assert DataframeContentUsage.extract_collection_name(1.5) is None
        assert DataframeContentUsage.extract_collection_name(True) is None

    def test_repeated_strings_hit_cache(self):
        """Repeated identical inputs are served from the lru_cache."""
        _extract_collection_name_cached.cache_clear()
        for _ in range(50):
            assert DataframeContentUsage.extract_collection_name('ansible.builtin.copy') == 'ansible.builtin'
        info = _extract_collection_name_cached.cache_info()
        assert info.misses == 1
        assert info.hits == 49

    def test_series_map_matches_scalar_results(self):
        series = pd.Series(['ansible.builtin.copy', 'copy', None, float('nan'), 'a.b.c.d'])
        result = series.map(DataframeContentUsage.extract_collection_name)
        assert result[0] == 'ansible.builtin'
        assert result[4] == 'a.b'
        # pandas turns None results into NaN inside a Series; the old .apply() path did too
        assert pd.isna(result[1])
        assert pd.isna(result[2])
        assert pd.isna(result[3])


# ---------------------------------------------------------------------------
# extract_role_name
# ---------------------------------------------------------------------------


class TestExtractRoleName:
    def test_fqcn_role_extracts_three_part_name(self):
        """namespace.collection.role -> namespace.collection.role"""
        result = DataframeContentUsage.extract_role_name('community.general.git_config')
        assert result == 'community.general.git_config'

    def test_four_part_fqcn_uses_role_segment(self):
        """For a.b.c.d the role is the third segment (c), not the trailing one."""
        result = DataframeContentUsage.extract_role_name('ansible.builtin.copy.something')
        assert result == 'ansible.builtin.copy'

    def test_three_part_fqcn_correct(self):
        result = DataframeContentUsage.extract_role_name('ansible.builtin.copy')
        assert result == 'ansible.builtin.copy'

    def test_standalone_two_part_role(self):
        """namespace.role -> namespace.role"""
        result = DataframeContentUsage.extract_role_name('my_ns.my_role')
        assert result == 'my_ns.my_role'

    def test_bare_single_part_returns_none(self):
        """single word -> None"""
        assert DataframeContentUsage.extract_role_name('copy') is None

    def test_none_input_returns_none(self):
        assert DataframeContentUsage.extract_role_name(None) is None

    def test_empty_string_returns_none(self):
        assert DataframeContentUsage.extract_role_name('') is None

    def test_redhat_namespace_role(self):
        result = DataframeContentUsage.extract_role_name('redhat.rhel_system_roles.selinux')
        assert result == 'redhat.rhel_system_roles.selinux'

    def test_deeply_nested_fqcn_uses_role_segment(self):
        """Extra trailing segments are ignored; the role stays the third segment."""
        result = DataframeContentUsage.extract_role_name('a.b.c.d.e')
        assert result == 'a.b.c'

    def test_trailing_junk_returns_none(self):
        """A malformed FQCN with non-word trailing junk no longer matches."""
        assert DataframeContentUsage.extract_role_name('ansible.builtin.copy.more extra') is None

    def test_invalid_characters_returns_none(self):
        assert DataframeContentUsage.extract_role_name('ns.my-role') is None
        assert DataframeContentUsage.extract_role_name('ns . role') is None

    def test_nan_returns_none(self):
        assert DataframeContentUsage.extract_role_name(float('nan')) is None

    def test_unhashable_inputs_return_none(self):
        """Guard must run before the lru_cache so unhashable values never reach it."""
        assert DataframeContentUsage.extract_role_name([]) is None
        assert DataframeContentUsage.extract_role_name({}) is None
        assert DataframeContentUsage.extract_role_name(['a.b.c']) is None
        assert DataframeContentUsage.extract_role_name({'a': 'b'}) is None

    def test_non_string_inputs_return_none(self):
        assert DataframeContentUsage.extract_role_name(42) is None
        assert DataframeContentUsage.extract_role_name(1.5) is None

    def test_repeated_strings_hit_cache(self):
        """Repeated identical inputs are served from the lru_cache."""
        _extract_role_name_cached.cache_clear()
        for _ in range(50):
            assert DataframeContentUsage.extract_role_name('community.general.git_config') == 'community.general.git_config'
        info = _extract_role_name_cached.cache_info()
        assert info.misses == 1
        assert info.hits == 49

    def test_series_map_matches_scalar_results(self):
        series = pd.Series(['my_ns.my_role', 'ansible.builtin.copy', 'plain', None, float('nan')])
        result = series.map(DataframeContentUsage.extract_role_name)
        assert result[0] == 'my_ns.my_role'
        assert result[1] == 'ansible.builtin.copy'
        # pandas turns None results into NaN inside a Series; the old .apply() path did too
        assert pd.isna(result[2])
        assert pd.isna(result[3])
        assert pd.isna(result[4])


# ---------------------------------------------------------------------------
# collection_regexp / standalone_role_regexp
# ---------------------------------------------------------------------------


class TestRegexpPatterns:
    def test_collection_regexp_is_non_empty_string(self):
        pattern = DataframeContentUsage.collection_regexp()
        assert isinstance(pattern, str)
        assert len(pattern) > 0

    def test_standalone_role_regexp_is_non_empty_string(self):
        pattern = DataframeContentUsage.standalone_role_regexp()
        assert isinstance(pattern, str)
        assert len(pattern) > 0

    def test_regexp_matches_precompiled_patterns(self):
        """The accessors stay backward-compatible with the precompiled patterns."""
        assert DataframeContentUsage.collection_regexp() == r'^(\w+)\.(\w+)\.(\w+)(?:\.\w+)*$'
        assert DataframeContentUsage.standalone_role_regexp() == r'^(\w+)\.(\w+)$'
