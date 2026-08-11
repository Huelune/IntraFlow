from __future__ import annotations

from dataclasses import dataclass
from platform import node
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import Device, User
from intraflow.services.errors import ValidationError
from intraflow.timeutil import utc_now_iso


@dataclass(frozen=True, slots=True)
class ProvisionedIdentity:
    user_id: str
    device_id: str
    device_name: str


class SetupService:
    """Creates the local identity needed before the normal workflow can start."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def provision(self, user_code: str, display_name: str, device_name: str | None = None) -> ProvisionedIdentity:
        user_code = user_code.strip()
        display_name = display_name.strip()
        resolved_device_name = (device_name or node() or "This PC").strip()
        if not user_code or not display_name:
            raise ValidationError("user code and display name are required")
        if not resolved_device_name:
            raise ValidationError("device name is required")

        now = utc_now_iso()
        user_id = str(uuid4())
        device_id = str(uuid4())
        with self.session_factory.begin() as session:
            user = session.scalar(select(User).where(User.user_code == user_code))
            if user is None:
                user = User(
                    id=user_id,
                    user_code=user_code,
                    display_name=display_name,
                    is_system_admin=0,
                    is_active=1,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                )
                session.add(user)
            elif not user.is_active:
                raise ValidationError("the configured user is inactive")
            else:
                user_id = user.id
            session.add(Device(
                id=device_id,
                user_id=user_id,
                device_name=resolved_device_name,
                is_current=1,
                created_at=now,
            ))
        return ProvisionedIdentity(user_id=user_id, device_id=device_id, device_name=resolved_device_name)
