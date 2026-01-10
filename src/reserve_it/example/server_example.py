import os
from pathlib import Path
from typing import Self

import uvicorn
from pydantic import model_validator

from reserve_it import ReservationRequest, build_app


# This subclass handles password validation, from the password field defined in
# `app-config-examples.yaml` under `custom_form_fields`
class PasswordProtectedRequest(ReservationRequest):
    password: str

    @model_validator(mode="after")
    def check_password(self) -> Self:
        if self.password != os.getenv("PASSWORD"):
            raise ValueError("Invalid input")
        return self


PROJECT_ROOT = Path(__file__).parent

if __name__ == "__main__":
    app = build_app(
        app_config=PROJECT_ROOT / "app-config-example.yaml",
        resource_config_path=PROJECT_ROOT / "resource-config-examples",
        sqlite_dir=PROJECT_ROOT / "sqlite_dbs",
        gcal_cred_path=PROJECT_ROOT / "client_secret.json",
        gcal_token_path=PROJECT_ROOT / "auth_token.json",
        request_classes=PasswordProtectedRequest,
    )
    uvicorn.run(app, host="127.0.0.1", port=8000)
