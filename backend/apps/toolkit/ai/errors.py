"""Turning model layer failures into API answers, for the calls that are not jobs."""

from rest_framework import exceptions

from apps.toolkit.ai.runner import CeilingReached
from apps.toolkit.jobs.services import JobFailed, TransientError


class AIUnavailable(exceptions.APIException):
    status_code = 503
    default_code = "ai_unavailable"
    default_detail = "The assistant is busy. Please try again in a moment."


class AIFailed(exceptions.APIException):
    status_code = 502
    default_code = "ai_failed"
    default_detail = "The assistant could not do that. Please try again."


class AICeiling(exceptions.Throttled):
    default_code = "ai_daily_limit"
    default_detail = "You have reached today's limit for assistant requests. Try again tomorrow."


def translate(exc: Exception) -> exceptions.APIException:
    if isinstance(exc, CeilingReached):
        return AICeiling(wait=3600)
    if isinstance(exc, TransientError):
        return AIUnavailable()
    if isinstance(exc, JobFailed):
        return AIFailed(detail=exc.detail or None)
    raise exc
