import os
from pathlib import Path
from typing import Self

import uvicorn
from pydantic import model_validator

from reserve_it import CustomFormField, ReservationRequest, build_app

# This defines a password form field that is added to all resource reservation webpages
PASSWORD_FIELD = CustomFormField(
    type="password", name="password", label="Password", required=True
)


# This subclass handles password validation
class PasswordProtectedRequest(ReservationRequest):
    password: str

    @model_validator(mode="after")
    def check_password(self) -> Self:
        if self.password != os.getenv("PASSWORD"):
            raise ValueError("Invalid input")
        return self


SRC_ROOT = Path(__file__).parents[3]

if __name__ == "__main__":
    app = build_app(
        title="Reserve-It Form Server Example",
        description="Form server for shared community amenity/resource reservations.",
        resource_config_path=SRC_ROOT / "resource-config-examples",
        sqlite_db_path=SRC_ROOT / "sqlite_dbs",
        gcal_cred_path=SRC_ROOT / "client_secret.json",
        gcal_token_path=SRC_ROOT / "auth_token.json",
        custom_form_fields=PASSWORD_FIELD,
        request_classes=PasswordProtectedRequest,
        version="0.1.0",
    )
    uvicorn.run(app, host="127.0.0.1", port=8000)
