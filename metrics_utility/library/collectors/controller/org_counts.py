"""Collector for per-organization user and team counts."""

from ..util import DictOutput, collector


@collector
def org_counts(*, db=None, output=DictOutput()):
    """Return user and team counts keyed by organization ID."""
    query = """
        WITH user_counts AS (
            SELECT
                main_rbac_roles.id AS role_id,
                COUNT(DISTINCT main_rbac_roles_members.user_id) AS num_users
            FROM main_rbac_roles
            JOIN main_rbac_roles_members
                ON main_rbac_roles_members.role_id = main_rbac_roles.id
            GROUP BY main_rbac_roles.id
        ), team_counts AS (
            SELECT organization_id, COUNT(*) AS num_teams
            FROM main_team
            GROUP BY organization_id
        )
        SELECT
            main_organization.id,
            main_organization.name,
            COALESCE(user_counts.num_users, 0) AS num_users,
            COALESCE(team_counts.num_teams, 0) AS num_teams
        FROM main_organization
        LEFT JOIN user_counts
            ON user_counts.role_id = main_organization.member_role_id
        LEFT JOIN team_counts
            ON team_counts.organization_id = main_organization.id
    """
    counts = {}
    with db.cursor() as cursor:
        cursor.execute(query)
        for org_id, name, num_users, num_teams in cursor.fetchall():
            counts[org_id] = {
                'name': name,
                'users': num_users,
                'teams': num_teams,
            }
    return output.dict(counts)
