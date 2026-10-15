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


class AICeiling(exceptions.APIException):
    status_code = 429
    default_code = "ai_daily_limit"
    default_detail = "You have reached today's limit for AI help. It resets tomorrow."


class AIOff(exceptions.APIException):
    status_code = 503
    default_code = "ai_off"
    default_detail = "AI writing is not switched on yet. Everything else works."


def translate(exc: Exception) -> exceptions.APIException:
    if isinstance(exc, CeilingReached):
        return AICeiling(detail=exc.detail or None)
    if isinstance(exc, JobFailed) and exc.code == "ai_off":
        return AIOff(detail=exc.detail or None)
    if isinstance(exc, TransientError):
        return AIUnavailable()
    if isinstance(exc, JobFailed):
        return AIFailed(detail=exc.detail or None)
    raise exc
