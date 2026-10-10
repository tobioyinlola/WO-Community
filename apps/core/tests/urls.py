"""URL configuration used only by the policy framework tests."""

from django.urls import path
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.core.serializers import StrictSerializer


class NoPolicyView(APIView):
    def get(self, request):
        return Response({"reached": True})


class PublicView(APIView):
    policy = policies.public

    def get(self, request):
        return Response({"reached": True})


class MemberView(APIView):
    policy = policies.active_member

    def get(self, request):
        return Response({"reached": True})


class EditorView(APIView):
    policy = policies.has_permission("editorial.manage")

    def get(self, request):
        return Response({"reached": True})


class EchoSerializer(StrictSerializer):
    name = serializers.CharField(max_length=10)


class EchoView(APIView):
    policy = policies.authenticated

    def post(self, request):
        serializer = EchoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class BoomView(APIView):
    policy = policies.public

    def get(self, request):
        raise RuntimeError("secret internal detail")


urlpatterns = [
    path("nopolicy", NoPolicyView.as_view()),
    path("public", PublicView.as_view()),
    path("member", MemberView.as_view()),
    path("editor", EditorView.as_view()),
    path("echo", EchoView.as_view()),
    path("boom", BoomView.as_view()),
]
