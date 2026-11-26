"""Base class for all anonymized rollup processors."""

import math

import numpy as np
import pandas as pd

from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_float_dtype,
    is_integer_dtype,
    is_object_dtype,
    is_string_dtype,
    is_timedelta64_dtype,
)


# Floats whose magnitude reaches this limit can no longer be represented exactly
# as int64, so they need a (rare) Python-int fallback to stay exact.
_MAX_EXACT_FLOAT_INT = 2**53


def _id_value_to_string(value):
    """Convert a single identifier value to its canonical string form.

    Mirrors the historical per-element rule used by
    ``_convert_id_columns_to_strings``: integral numbers become
    ``str(int(value))`` (``bool`` is an ``int`` subclass, so ``True`` -> ``'1'``),
    while everything else (strings, ``None``, ``NaN``/``NA``, non-integral
    floats, arbitrary objects) is returned unchanged. ``inf`` is also returned
    unchanged instead of raising ``OverflowError``.
    """
    if isinstance(value, int):
        return str(int(value))
    if isinstance(value, float) and pd.notna(value) and math.isfinite(value) and value == int(value):
        return str(int(value))
    return value


class BaseAnonymizedRollup:
    """Base class for all anonymized rollup processors.

    Subclasses implement ``prepare``, ``merge``, and ``base`` to define how
    raw collector data is aggregated into a JSON structure suitable for
    inclusion in the anonymized daily report.
    """

    # Identifier columns converted to strings before aggregation/JSON output.
    # Subclasses may extend this tuple with additional ID columns.
    _ID_COLUMNS = ('id', 'job_id', 'host_id', 'job_remote_id')

    def __init__(self, rollup_name: str):
        """Initialize the rollup with a name identifier.

        Args:
            rollup_name: Unique name for this rollup (used as a directory key when saving).
        """
        self.rollup_name = rollup_name
        self.collector_names = []

    # Merges two data (it dont have to be dataframes if overriden)
    # this is used in batch processing
    # where we need to merge partial rollup with current batch aggregation
    def merge(self, dataframe_all, dataframe_new):
        """Combine accumulated rollup data with a new batch.

        The default implementation concatenates two DataFrames.  Subclasses may
        override this method for non-DataFrame data structures or custom merge logic.

        Args:
            dataframe_all: The accumulated data so far (may be None on the first call).
            dataframe_new: The freshly prepared batch to merge in.

        Returns:
            The merged data (a concatenated DataFrame by default).
        """
        if dataframe_all is None:
            return dataframe_new

        return pd.concat([dataframe_all, dataframe_new], ignore_index=True)

    @staticmethod
    def _convert_id_column_to_strings(series):
        """Vectorised equivalent of applying ``_id_value_to_string`` element-wise.

        Behaviours preserved from the previous ``.apply(lambda ...)`` implementation:

        * integer dtypes (``int64``, ``int32``, nullable ``Int64``/``UInt64``) ->
          ``str(int(value))`` for every non-null value, nulls untouched;
        * float dtypes -> whole finite numbers become int strings, ``NaN`` and
          fractional floats are left as-is;
        * string dtypes -> already strings, returned untouched;
        * datetime/timedelta dtypes -> returned untouched;
        * mixed ``object`` columns -> per-value conversion, so numeric strings
          such as ``'007'`` (leading zeros) are left untouched.

        Args:
            series: A pandas Series holding identifier values.

        Returns:
            A Series where integral numeric values have been converted to strings.
        """
        dtype = series.dtype

        # String-backed columns are already in the target form; nothing to do.
        # ``object`` columns are handled below because they may mix types.
        if is_string_dtype(dtype) and not is_object_dtype(dtype):
            return series

        # Datetime-like columns cannot hold numeric IDs; leave them untouched.
        if is_datetime64_any_dtype(dtype) or is_timedelta64_dtype(dtype):
            return series

        # Integer columns (including nullable Int*/UInt*) only hold integral values.
        if is_integer_dtype(dtype) and not is_bool_dtype(dtype):
            if not series.isna().any():
                return series.astype(str).astype(object)

            mask = series.notna()
            result = series.astype(object)
            if mask.any():
                result.loc[mask] = series[mask].astype(str)
            return result

        if is_float_dtype(dtype):
            result = series.astype(object)
            # Work on a plain numpy float array so pd.NA/Nullable masks cannot leak
            # into the boolean masks used for assignment.
            values = series.to_numpy(dtype='float64', na_value=np.nan)
            finite = np.isfinite(values)
            whole = pd.Series(finite & (values % 1 == 0), index=series.index)
            if whole.any():
                safe = whole & pd.Series(np.abs(values) < _MAX_EXACT_FLOAT_INT, index=series.index)
                if safe.any():
                    result.loc[safe] = values[safe.to_numpy()].astype(np.int64).astype(str)
                # Floats beyond the int64 range need Python ints to stay exact.
                for pos in np.flatnonzero((whole & ~safe).to_numpy()):
                    result.iloc[pos] = str(int(values[pos]))
            return result

        # Mixed object columns (or unusual dtypes such as bool): convert value by
        # value, which keeps leading-zero strings and other objects intact.
        return pd.Series([_id_value_to_string(value) for value in series], index=series.index, dtype=object)

    def _convert_id_columns_to_strings(self, dataframe):
        """Convert ID columns to strings at the beginning of prepare().

        Converts numeric ID columns (see ``_ID_COLUMNS``) to strings to ensure
        consistent JSON serialization.
        """
        if dataframe.empty:
            return dataframe

        for col in self._ID_COLUMNS:
            if col in dataframe.columns:
                # Convert numeric IDs to strings, preserving NaN values
                dataframe[col] = self._convert_id_column_to_strings(dataframe[col])

        return dataframe

    # takes raw data and computes aggregation
    # this works in batches, for example we are collecting every hour
    # this hourly data arrive into prepare, then it gets merged with partial rollup (initaly empty)
    def prepare(self, dataframe):
        """Transform a raw batch DataFrame into the intermediate rollup structure.

        Called once per hourly (or other interval) batch.  The result is later
        passed to ``merge`` to accumulate across batches.

        Args:
            dataframe: Raw pandas DataFrame from the collector.

        Returns:
            Transformed data (DataFrame or JSON-serialisable structure).
        """
        return dataframe

    # Base receive the full daily rollup and computes some final statistics for the day
    def base(self, dataframe):
        """Compute final daily statistics from the fully-merged rollup data.

        Args:
            dataframe: The accumulated rollup data produced by successive calls to
                ``merge`` across all batches for the day.

        Returns:
            An empty DataFrame by default; subclasses return a dict with a
            ``'json'`` key containing the final JSON payload.
        """
        return pd.DataFrame()
