"""
MediExplain AI — Application Configuration
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import pytz

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILES = (str(_BACKEND_DIR / ".env"), ".env", "backend/.env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, case_sensitive=True, extra="allow")
    # App
    APP_ENV: str = "development"
    BACKEND_SECRET_KEY: str = "change-me-in-production"
    TIMEZONE: str = "Asia/Kolkata"
    MAX_UPLOAD_SIZE_MB: int = 20

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    ALLOWED_ORIGIN_REGEX: str = r"^https:\/\/.*\.vercel\.app$"

    @property
    def ALLOWED_ORIGINS_LIST(self) -> List[str]:
        raw = self.ALLOWED_ORIGINS or ""
        origins = []
        for o in raw.split(","):
            clean = o.strip().strip("'\"").rstrip("/")
            if clean:
                origins.append(clean)
        if not origins:
            origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
        return origins

    @property
    def TZ(self):
        return pytz.timezone(self.TIMEZONE)

    # Supabase (Admin client uses service role key)
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # AI (Google Gemini)
    AI_API_KEY: str = ""
    AI_MODEL: str = "gemini-3.8-flash"

    # Razorpay (Payment Gateway - Test mode initially)
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_PLAN_ID: str = ""

    # Admin
    ADMIN_EMAIL: str = ""

    # Subscription business model constants
    TRIAL_DAYS: int = 30
    GRACE_PERIOD_HOURS: int = 72
    GRACE_PERIOD_DAYS: int = 3
    PLAN_AMOUNT_PAISE: int = 20000  # ₹200
    PLAN_CURRENCY: str = "INR"
    PLAN_INTERVAL: str = "monthly"


settings = Settings()
