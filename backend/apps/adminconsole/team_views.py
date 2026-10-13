"""The console team: what each role may do, and who holds it.

Only a super admin (the `roles.manage` permission) can change who is on the team. Giving or
taking a role needs a fresh two step check, signs the person out everywhere so the change applies
at once, and is written to the audit log. Nobody can change their own roles, and the last super
admin cannot be demoted.
"""

from uuid import UUID

from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts
from apps.accounts.models import User, UserRole
from apps.adminconsole.views import _actor, _ip
from apps.audit import services as audit
from apps.core import policies
from apps.core.errors import ConflictError
from apps.core.rbac import ADMIN_ROLES, PERMISSIONS_BY_ROLE, Role
from apps.core.serializers import StrictSerializer

TEAM_ROLES = [r.value for r in (Role.CONTENT_EDITOR, Role.COMMUNITY_ADMIN, Role.SUPER_ADMIN)]
LABELS = {
    "member": "Member",
    "mentor": "Mentor",
    "content_editor": "Content editor",
    "community_admin": "Community admin",
    "super_admin": "Super admin",
}
BLURBS = {
    "member": "Uses the community: profile, feed, jobs, learning and the toolkit.",
    "mentor": "A member who also takes mentoring sessions.",
    "content_editor": "Writes news and awards, runs courses and reviews jobs.",
    "community_admin": "Runs the community: members, events, email, moderation and support.",
    "super_admin": "Everything, plus the team, settings and the audit log.",
}
VIEW = policies.admin_permission("members.view")
MANAGE = policies.admin_permission("roles.manage", step_up=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
}


class RoleSerializer(serializers.Serializer):
    role = serializers.CharField()
    title = serializers.CharField()
    blurb = serializers.CharField()
    permissions = serializers.ListField(child=serializers.CharField())
    people = serializers.IntegerField()
    team = serializers.BooleanField(help_text="Whether it is a console role you can invite to")


class ChangeRoleSerializer(StrictSerializer):
    role = serializers.ChoiceField(choices=TEAM_ROLES)
    action = serializers.ChoiceField(choices=["grant", "revoke"])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class RoleHolderSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    roles = serializers.ListField(child=serializers.CharField())


class RolesView(APIView):
    policy = VIEW

    @extend_schema(
        summary="Roles and what each can do",
        description="The permission matrix, from the same table the API enforces.",
        responses={200: RoleSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        counts: dict[str, int] = {}
        for (role,) in UserRole.objects.filter(user__status="active").values_list("role"):
            counts[role] = counts.get(role, 0) + 1
        rows = [
            {
                "role": role.value,
                "title": LABELS[role.value],
                "blurb": BLURBS[role.value],
                "permissions": sorted(PERMISSIONS_BY_ROLE[role]),
                "people": counts.get(role.value, 0),
                "team": role in ADMIN_ROLES,
            }
            for role in Role
        ]
        return Response(RoleSerializer(rows, many=True).data)


class ChangeRoleView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Give or take a console role",
        description="Super admin only. Ends the person's sessions so the change applies at once.",
        request=ChangeRoleSerializer,
        responses={
            200: RoleHolderSerializer,
            **ERRORS,
            404: OpenApiResponse(description="No such account"),
            409: OpenApiResponse(description="That would leave no super admin"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        serializer = ChangeRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = serializer.validated_data["role"]
        action = serializer.validated_data["action"]
        actor = _actor(request)
        if actor.pk == user_id:
            raise exceptions.PermissionDenied("You cannot change your own roles.")
        with transaction.atomic():
            target = User.objects.select_for_update().filter(pk=user_id).first()
            if target is None:
                raise exceptions.NotFound()
            if target.status != "active":
                raise ConflictError(
                    "Only an active account can be given a console role.", code="not_active"
                )
            before = sorted(target.role_names())
            if action == "grant":
                accounts.grant_role(user_id, role)
            else:
                if role == Role.SUPER_ADMIN.value and not (
                    UserRole.objects.filter(role=role, user__status="active")
                    .exclude(user_id=user_id)
                    .exists()
                ):
                    raise ConflictError(
                        "There must always be at least one super admin.", code="last_super_admin"
                    )
                accounts.revoke_role(user_id, role)
            # Roles are read per request, but a token made earlier still carries the old claims.
            target.bump_token_version()
            after = sorted(UserRole.objects.filter(user_id=user_id).values_list("role", flat=True))
            audit.record(
                actor=actor,
                action=f"role.{action}",
                target_type="user",
                target_id=user_id,
                before={"roles": before},
                after={"roles": after, "role": role},
                reason=serializer.validated_data["reason"],
                ip=_ip(request),
            )
        return Response(
            RoleHolderSerializer({"id": user_id, "email": target.email, "roles": after}).data
        )
