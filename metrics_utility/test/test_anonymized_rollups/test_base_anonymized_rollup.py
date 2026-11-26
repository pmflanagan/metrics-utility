"""Tests for BaseAnonymizedRollup identifier column conversion."""

import numpy as np
import pandas as pd
import pytest

from metrics_utility.anonymized_rollups.base_anonymized_rollup import BaseAnonymizedRollup
from metrics_utility.anonymized_rollups.jobhostsummary_anonymized_rollup import JobHostSummaryAnonymizedRollup


def _legacy_convert(series):
    """Reference implementation: the pre-vectorization ``.apply(lambda ...)`` rule."""
    return series.apply(lambda x: str(int(x)) if pd.notna(x) and isinstance(x, (int, float)) and x == int(x) else x)


def _assert_same_values(result, expected):
    """Assert two converted series hold the same values, treating NA variants as equal.

    Nullable dtypes can surface ``pd.NA`` where the legacy ``.apply`` produced
    ``np.nan`` (or vice versa); both are "missing" and must compare equal.
    """
    assert len(result) == len(expected)
    for got, exp in zip(result, expected):
        if pd.isna(got) and pd.isna(exp):
            continue
        assert got == exp
        assert type(got) is type(exp), f'{got!r} ({type(got)}) vs {exp!r} ({type(exp)})'


@pytest.mark.parametrize(
    'series',
    [
        pd.Series([1, 2, 3], dtype='int64'),
        pd.Series([1, 2, 3], dtype='int32'),
        pd.Series([1, 2], dtype='UInt64'),
        pd.Series([1, None, 3], dtype='Int64'),
        pd.Series([1.0, 2.0, np.nan, 1.5], dtype='float64'),
        pd.Series([1.0, None, 1.5], dtype='Float64'),
        pd.Series(['1', '007', None], dtype='str'),
        pd.Series(['1', 2, 3.0, 3.5, None, np.nan, '007'], dtype=object),
        pd.Series([True, False]),
        pd.Series(pd.to_datetime(['2024-01-01', None])),
        pd.Series([], dtype='int64'),
    ],
    ids=[
        'int64',
        'int32',
        'UInt64',
        'Int64_nullable',
        'float64',
        'Float64_nullable',
        'string_dtype',
        'object_mixed',
        'bool',
        'datetime',
        'empty',
    ],
)
def test_convert_id_column_matches_legacy(series):
    """The vectorized helper must match the legacy per-element conversion exactly."""
    result = BaseAnonymizedRollup._convert_id_column_to_strings(series)
    _assert_same_values(result, _legacy_convert(series))


def test_convert_id_column_preserves_leading_zeros():
    """Numeric-looking strings are already strings and must never be re-parsed."""
    series = pd.Series(['007', '1', 7], dtype=object)

    result = BaseAnonymizedRollup._convert_id_column_to_strings(series)

    assert result.tolist() == ['007', '1', '7']


def test_convert_id_column_keeps_fractional_floats():
    series = pd.Series([1.0, 1.5, 2.0, np.nan])

    result = BaseAnonymizedRollup._convert_id_column_to_strings(series)

    values = result.tolist()
    assert values[0] == '1'
    assert values[1] == 1.5
    assert values[2] == '2'
    assert pd.isna(values[3])


def test_convert_id_column_keeps_non_finite_floats():
    """``inf`` must stay untouched (the legacy lambda raised OverflowError here)."""
    series = pd.Series([np.inf, -np.inf, np.nan, 2.0])

    result = BaseAnonymizedRollup._convert_id_column_to_strings(series)

    values = result.tolist()
    assert values[0] == np.inf
    assert values[1] == -np.inf
    assert pd.isna(values[2])
    assert values[3] == '2'


def test_convert_id_column_keeps_huge_float_exact():
    """Whole floats beyond int64 range fall back to Python ints."""
    series = pd.Series([1e300])

    result = BaseAnonymizedRollup._convert_id_column_to_strings(series)

    assert result.tolist() == [str(int(1e300))]


def test_convert_id_columns_to_strings_dataframe():
    rollup = BaseAnonymizedRollup('test')
    dataframe = pd.DataFrame(
        {
            'id': pd.Series([1, 2], dtype='int64'),
            'job_id': pd.Series([10, None], dtype='Int64'),
            'host_id': pd.Series([1.0, 2.5]),
            'job_remote_id': pd.Series(['007', '8'], dtype=object),
            'other_numeric': [1, 2],
        }
    )

    result = rollup._convert_id_columns_to_strings(dataframe)

    assert result['id'].tolist() == ['1', '2']
    assert result['job_id'].tolist()[0] == '10'
    assert pd.isna(result['job_id'].tolist()[1])
    assert result['host_id'].tolist() == ['1', 2.5]
    assert result['job_remote_id'].tolist() == ['007', '8']
    # Non-ID columns are untouched
    assert result['other_numeric'].tolist() == [1, 2]


def test_convert_id_columns_to_strings_empty_dataframe():
    rollup = BaseAnonymizedRollup('test')
    dataframe = pd.DataFrame({'id': pd.Series([], dtype='int64')})

    result = rollup._convert_id_columns_to_strings(dataframe)

    assert result.empty


def test_jobhostsummary_id_columns_include_host_remote_id():
    assert JobHostSummaryAnonymizedRollup._ID_COLUMNS == ('id', 'job_id', 'host_id', 'job_remote_id', 'host_remote_id')


def test_jobhostsummary_converts_host_remote_id():
    rollup = JobHostSummaryAnonymizedRollup()
    dataframe = pd.DataFrame({'job_remote_id': pd.Series([1001, 1002], dtype='int64'), 'host_remote_id': pd.Series([1, 2], dtype='int64')})

    result = rollup._convert_id_columns_to_strings(dataframe)

    assert result['job_remote_id'].tolist() == ['1001', '1002']
    assert result['host_remote_id'].tolist() == ['1', '2']
