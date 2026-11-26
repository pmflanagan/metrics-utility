"""Dataframe engine for content (module/collection/role) usage from main_jobevent."""

import functools
import re

from metrics_utility.automation_controller_billing.dataframe_engine.base import Base


# Precompiled patterns.  These are the single source of truth for the
# ``collection_regexp()`` / ``standalone_role_regexp()`` accessors below.
_COLLECTION_RE = re.compile(r'^(\w+)\.(\w+)\.(\w+)(?:\.\w+)*$')
_STANDALONE_ROLE_RE = re.compile(r'^(\w+)\.(\w+)$')


@functools.lru_cache(maxsize=4096)
def _extract_collection_name_cached(x: str) -> str | None:
    """Cached core of :meth:`DataframeContentUsage.extract_collection_name`.

    Callers must guarantee ``x`` is a ``str`` so that only hashable values
    reach the cache.

    Args:
        x: Module name string.

    Returns:
        Two-part collection name string, or None.
    """
    if '.' not in x:
        return None

    m = _COLLECTION_RE.match(x)

    return f'{m.group(1)}.{m.group(2)}' if m else None


@functools.lru_cache(maxsize=4096)
def _extract_role_name_cached(x: str) -> str | None:
    """Cached core of :meth:`DataframeContentUsage.extract_role_name`.

    Callers must guarantee ``x`` is a ``str`` so that only hashable values
    reach the cache.

    Args:
        x: Role name string.

    Returns:
        Normalised role name string, or None.
    """
    if '.' not in x:
        return None

    collection_role = _COLLECTION_RE.match(x)
    if collection_role:
        return f'{collection_role.group(1)}.{collection_role.group(2)}.{collection_role.group(3)}'

    standalone_role = _STANDALONE_ROLE_RE.match(x)
    if standalone_role:
        return f'{standalone_role.group(1)}.{standalone_role.group(2)}'

    return None


# dataframe for main_jobevent
class DataframeContentUsage(Base):
    """Aggregates task runs by host/module/collection/role from main_jobevent CSV batches."""

    def build_dataframe(self):
        # A monthly rollup dataframe
        content_explorer_rollup = None

        for date in self.dates():
            ###############################
            # Start a daily rollup code here
            ###############################
            for data in self.extractor.iter_batches(date=date, collections=['main_jobevent'], optional=['config']):
                # If the dataframe is empty, skip additional processing
                events = data['main_jobevent']
                if events.empty:
                    continue

                # Filter non relevant rows
                events = events[events['task_action'].notnull()]
                events = events[events['host_name'].notnull()]

                # If the dataframe is empty, skip additional processing
                if events.empty:
                    continue

                events['install_uuid'] = data['config']['install_uuid']

                # If resolved_action resolved role are not there, fill them with task action
                # and role
                events['task_action'] = events.resolved_action.fillna(events.task_action).astype(str)
                events['role'] = events.resolved_role.fillna(events.role).astype(str)
                # Only get valid role names into role name
                events['role'] = events['role'].map(self.extract_role_name)

                # Rename columns to match the reality, they are just names, not normalized cols anymore
                events.rename(columns={'task_action': 'module_name', 'role': 'role_name'}, inplace=True)

                events['collection_name'] = events['module_name'].map(self.extract_collection_name)

                # Final cleanup if some module names didn't connect, otherwise this will fail
                # to insert with not null constraint on module_name
                events = events[events['module_name'].notnull()]

                # Set a human readable values for missing role and collection name
                events['role_name'] = events['role_name'].fillna('No role used').astype(str)
                events['collection_name'] = events['collection_name'].fillna('No collection used').astype(str)

                ################################
                # Do the aggregation
                ################################

                events_group = self.group(events)

                ################################
                # Merge aggregations of multiple batches
                ################################

                content_explorer_rollup = self.merge(content_explorer_rollup, events_group)

        if content_explorer_rollup is None or content_explorer_rollup.empty:
            return self.empty()

        return content_explorer_rollup.reset_index()

    # Do the aggregation
    def group(self, dataframe):
        group = dataframe.groupby(self.unique_index_columns(), dropna=False).agg(
            task_runs=('module_name', 'count'),
            duration=('duration', 'sum'),
        )

        # Duration is null in older versions of Controller
        group['duration'] = group.duration.fillna(0)

        # Tweak types to match the table
        return self.cast_dataframe(group, self.cast_types())

    # Merge pre-aggregated
    def regroup(self, dataframe):
        return dataframe.groupby(self.unique_index_columns(), dropna=False).agg(
            task_runs=('task_runs', 'sum'),
            duration=('duration', 'sum'),
        )

    @staticmethod
    def collection_regexp():
        """Return the regex pattern for matching fully-qualified collection module names.

        Returns:
            Regex pattern string.
        """
        return _COLLECTION_RE.pattern

    @staticmethod
    def standalone_role_regexp():
        """Return the regex pattern for matching standalone two-part role names.

        Returns:
            Regex pattern string.
        """
        return _STANDALONE_ROLE_RE.pattern

    @staticmethod
    def extract_collection_name(x):
        """Extract the ``namespace.collection`` prefix from a fully-qualified module name.

        Args:
            x: Module name string or None.

        Returns:
            Two-part collection name string, or None.
        """
        if not isinstance(x, str):
            return None

        return _extract_collection_name_cached(x)

    @staticmethod
    def extract_role_name(x):
        """Extract a normalised role name from a fully-qualified or standalone role string.

        Args:
            x: Role name string or None.

        Returns:
            Normalised role name string, or None.
        """
        if not isinstance(x, str):
            return None

        return _extract_role_name_cached(x)

    @staticmethod
    def unique_index_columns():
        return ['host_name', 'module_name', 'collection_name', 'role_name', 'install_uuid', 'job_remote_id']

    @staticmethod
    def data_columns():
        return ['task_runs', 'duration']

    @staticmethod
    def cast_types():
        return {'duration': 'float64', 'task_runs': 'int64'}

    @staticmethod
    def operations():
        return {}
