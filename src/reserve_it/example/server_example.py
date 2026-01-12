import os
from pathlib import Path
from typing import Self

import uvicorn
from pydantic import model_validator

from reserve_it import ReservationRequest, build_app


# This subclass handles password validation, from the password field defined in
# `app-config.yaml` under `custom_form_fields`
class PasswordProtectedRequest(ReservationRequest):
    password: str

    @model_validator(mode="after")
    def check_password(self) -> Self:
        if self.password != os.getenv("PASSWORD"):
            raise ValueError("Invalid input")
        return self


PROJECT_ROOT = Path(__file__).parent
GCAL_CREDS_DIR = PROJECT_ROOT / ".gcal-credentials"

if __name__ == "__main__":
    # NOTE: if PROJECT ROOT is your current working dir, these commented out Path args
    # are the defaults
    app = build_app(
        # app_config=PROJECT_ROOT / "app-config.yaml",
        # resource_config_path=PROJECT_ROOT / "resource-configs",
        # sqlite_dir=PROJECT_ROOT / "sqlite-dbs",
        # gcal_secret_path=GCAL_CREDS_DIR / "client-secret.json",
        # gcal_token_path=GCAL_CREDS_DIR / "auth-token.json",
        # site_dir=PROJECT_ROOT / "site",
        request_classes=PasswordProtectedRequest,
    )
    uvicorn.run(app, host="127.0.0.1", port=8000)
