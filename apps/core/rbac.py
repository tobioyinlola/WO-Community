"""Roles and the permission codes they carry.

The matrix lives in code so a change is reviewed like any other change and
needs no data migration. Codes follow ``<area>.<action>``.
"""

from enum import StrEnum


class Role(StrEnum):
    MEMBER = "member"
    MENTOR = "mentor"
    CONTENT_EDITOR = "content_editor"
    COMMUNITY_ADMIN = "community_admin"
    SUPER_ADMIN = "super_admin"


ADMIN_ROLES = frozenset({Role.CONTENT_EDITOR, Role.COMMUNITY_ADMIN, Role.SUPER_ADMIN})

_MEMBER = frozenset({"profile.edit", "feed.post", "jobs.post", "learning.enrol"})
_MENTOR = _MEMBER | {"mentorship.respond"}
_EDITOR = frozenset(
    {"admin.access", "editorial.manage", "courses.manage", "jobs.moderate"},
)
_COMMUNITY_ADMIN = _EDITOR | {
    "members.view",
    "directory.feature",
    "reference.manage",
    "members.approve",
    "members.suspend",
    "members.remove",
    "invitations.manage",
    "mentors.decide",
    "events.manage",
    "campaigns.send",
    "reports.handle",
}
_SUPER_ADMIN = _COMMUNITY_ADMIN | {"roles.manage", "audit.read", "settings.manage"}

PERMISSIONS_BY_ROLE: dict[Role, frozenset[str]] = {
    Role.MEMBER: _MEMBER,
    Role.MENTOR: _MENTOR,
    Role.CONTENT_EDITOR: _EDITOR,
    Role.COMMUNITY_ADMIN: frozenset(_COMMUNITY_ADMIN),
    Role.SUPER_ADMIN: frozenset(_SUPER_ADMIN),
}


def permissions_for(roles: "set[str] | frozenset[str] | list[str]") -> frozenset[str]:
    codes: set[str] = set()
    for name in roles:
        try:
            codes |= PERMISSIONS_BY_ROLE[Role(name)]
        except (ValueError, KeyError):
            continue
    return frozenset(codes)
