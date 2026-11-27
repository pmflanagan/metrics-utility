from unittest.mock import MagicMock

from metrics_utility.library.collectors.controller.org_counts import org_counts


def _make_mock_db(rows=()):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_db.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.return_value = list(rows)
    return mock_db, mock_cursor


def _query(mock_cursor):
    return mock_cursor.execute.call_args.args[0]


def test_org_counts_basic():
    """Test org_counts collector basic functionality."""
    mock_db = MagicMock()

    instance = org_counts(db=mock_db)

    assert hasattr(instance, 'gather')
    assert hasattr(instance, 'kwargs')
    assert instance.kwargs['db'] == mock_db


def test_org_counts_output():
    """Test org_counts returns expected dict structure."""
    mock_db, _mock_cursor = _make_mock_db(
        [
            (1, 'Default', 15, 3),
            (2, 'Engineering', 42, 7),
        ]
    )

    instance = org_counts(db=mock_db)
    result = instance.gather()

    assert isinstance(result, dict)
    assert len(result) == 2

    assert result[1] == {'name': 'Default', 'users': 15, 'teams': 3}
    assert result[2] == {'name': 'Engineering', 'users': 42, 'teams': 7}


def test_org_counts_empty():
    """Test org_counts handles empty result."""
    mock_db, _mock_cursor = _make_mock_db()

    instance = org_counts(db=mock_db)
    result = instance.gather()

    assert isinstance(result, dict)
    assert len(result) == 0


def test_org_counts_zero_members():
    """Test org_counts handles orgs with zero users and teams."""
    mock_db, _mock_cursor = _make_mock_db(
        [
            (10, 'Empty Org', 0, 0),
        ]
    )

    instance = org_counts(db=mock_db)
    result = instance.gather()

    assert result[10] == {'name': 'Empty Org', 'users': 0, 'teams': 0}


def test_org_counts_no_users_but_has_teams():
    """Test org_counts keeps team counts when there are no role members."""
    mock_db, _mock_cursor = _make_mock_db(
        [
            (11, 'Team Only Org', 0, 4),
        ]
    )

    result = org_counts(db=mock_db).gather()

    assert result[11] == {'name': 'Team Only Org', 'users': 0, 'teams': 4}


def test_org_counts_query_structure():
    """Test that the SQL query joins through role tables for user counts."""
    mock_db, mock_cursor = _make_mock_db()

    instance = org_counts(db=mock_db)
    instance.gather()

    query = _query(mock_cursor)

    assert 'main_organization' in query
    assert 'main_rbac_roles' in query
    assert 'main_rbac_roles_members' in query
    assert 'main_team' in query
    assert 'GROUP BY' in query


def test_org_counts_pre_aggregates_users_and_teams():
    """Test user and team counts are pre-aggregated in CTEs before joining."""
    mock_db, mock_cursor = _make_mock_db()

    org_counts(db=mock_db).gather()

    query = _query(mock_cursor)

    assert 'WITH user_counts AS' in query
    assert 'COUNT(DISTINCT main_rbac_roles_members.user_id) AS num_users' in query
    assert 'JOIN main_rbac_roles_members' in query
    assert 'ON main_rbac_roles_members.role_id = main_rbac_roles.id' in query
    assert 'GROUP BY main_rbac_roles.id' in query

    assert 'team_counts AS' in query
    assert 'SELECT organization_id, COUNT(*) AS num_teams' in query
    assert 'FROM main_team' in query
    assert 'GROUP BY organization_id' in query

    assert 'LEFT JOIN user_counts' in query
    assert 'ON user_counts.role_id = main_organization.member_role_id' in query
    assert 'LEFT JOIN team_counts' in query
    assert 'ON team_counts.organization_id = main_organization.id' in query

    assert 'COALESCE(user_counts.num_users, 0) AS num_users' in query
    assert 'COALESCE(team_counts.num_teams, 0) AS num_teams' in query

    # The old fan-out shape must be gone
    assert 'COUNT(DISTINCT main_team.id)' not in query
    assert 'GROUP BY main_organization.id' not in query
    assert 'LEFT JOIN main_team' not in query
