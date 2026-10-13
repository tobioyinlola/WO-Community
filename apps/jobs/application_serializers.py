from rest_framework import serializers

from apps.core.serializers import StrictSerializer

STATUSES = ["submitted", "reviewing", "shortlisted", "rejected", "hired", "withdrawn"]


class ApplyJobSerializer(StrictSerializer):
    note = serializers.CharField(max_length=2000, trim_whitespace=False)
    link = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


class DecideApplicationSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=["reviewing", "shortlisted", "rejected", "hired"])
    note = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class MyApplicationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=STATUSES)
    note = serializers.CharField()
    link = serializers.CharField()
    created_at = serializers.DateTimeField()
    decision_note = serializers.CharField()


class ApplicationApplicantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    email = serializers.EmailField()


class ApplicationRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=STATUSES)
    note = serializers.CharField()
    link = serializers.CharField()
    created_at = serializers.DateTimeField()
    decided_at = serializers.DateTimeField(allow_null=True)
    decision_note = serializers.CharField()
    applicant = ApplicationApplicantSerializer()
    job_id = serializers.UUIDField()
    job_title = serializers.CharField()
    job_organisation = serializers.CharField()
    job_status = serializers.CharField()


class AdminApplicationQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=STATUSES, required=False, default="")
    job_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    q = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)
