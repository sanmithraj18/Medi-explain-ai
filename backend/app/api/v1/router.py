"""
MediExplain AI — API v1 Router
Registers all endpoint modules.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    reports,
    analysis,
    questions,
    subscriptions,
    payments,
    webhooks,
    admin,
)

api_router = APIRouter()

api_router.include_router(auth.router,          prefix="/auth",          tags=["Authentication"])
api_router.include_router(reports.router,        prefix="/reports",       tags=["Medical Reports"])
api_router.include_router(analysis.router,       prefix="/analysis",      tags=["AI Analysis"])
api_router.include_router(questions.router,      prefix="/questions",     tags=["Doctor Questions"])
api_router.include_router(subscriptions.router,  prefix="/subscriptions", tags=["Subscriptions"])
api_router.include_router(payments.router,       prefix="/payments",      tags=["Payments"])
api_router.include_router(webhooks.router,       prefix="/webhooks",      tags=["Webhooks"])
api_router.include_router(webhooks.router,       prefix="/payments",      tags=["Webhooks"])
api_router.include_router(admin.router,          prefix="/admin",         tags=["Admin"])

