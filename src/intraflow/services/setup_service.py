from __future__ import annotations

from dataclasses import dataclass
from platform import node
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import Device, SyncOutbox, User
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
        """Backward-compatible alias for starting a new local team."""
        return self.start_new_team(user_code, display_name, device_name)

    def start_new_team(
        self, user_code: str, display_name: str, device_name: str | None = None,
    ) -> ProvisionedIdentity:
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
                    is_system_admin=1,
                    is_active=1,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                )
                session.add(user)
                session.add(SyncOutbox(
                    id=str(uuid4()), target_type="USERS", target_id="global",
                    created_at=now, retry_count=0,
                ))
            elif not user.is_active:
                raise ValidationError("비활성 사용자 코드입니다.")
            else:
                raise ValidationError("이미 존재하는 팀 사용자입니다. 기존 팀 합류를 사용하세요.")
            for previous in session.scalars(select(Device).where(Device.user_id == user_id, Device.is_current == 1)):
                previous.is_current = 0
            session.add(Device(
                id=device_id,
                user_id=user_id,
                device_name=resolved_device_name,
                is_current=1,
                created_at=now,
            ))
        return ProvisionedIdentity(user_id=user_id, device_id=device_id, device_name=resolved_device_name)

    def register_device_for_existing_user(
        self, user_id: str, device_name: str | None = None, *, session: Session | None = None,
    ) -> ProvisionedIdentity:
        resolved_device_name = (device_name or node() or "This PC").strip()
        if not resolved_device_name:
            raise ValidationError("PC 이름은 필수입니다.")

        def register(active_session: Session) -> ProvisionedIdentity:
            user = active_session.get(User, user_id)
            if user is None:
                raise ValidationError("NAS에서 선택한 사용자를 찾을 수 없습니다.")
            if not user.is_active:
                raise ValidationError("비활성 사용자는 이 PC에 연결할 수 없습니다.")
            existing = active_session.scalar(select(Device).where(
                Device.user_id == user_id,
                Device.device_name == resolved_device_name,
                Device.is_current == 1,
            ))
            if existing is not None:
                return ProvisionedIdentity(user_id, existing.id, resolved_device_name)
            device_id = str(uuid4())
            active_session.add(Device(
                id=device_id, user_id=user_id, device_name=resolved_device_name,
                is_current=1, created_at=utc_now_iso(),
            ))
            return ProvisionedIdentity(user_id, device_id, resolved_device_name)

        if session is not None:
            return register(session)
        with self.session_factory.begin() as active_session:
            return register(active_session)

    def ensure_bootstrap_admin(self, user_id: str) -> None:
        """Promote only the sole user in a legacy empty installation."""
        with self.session_factory.begin() as session:
            user = session.get(User, user_id)
            if user is None:
                raise ValidationError("현재 사용자를 찾을 수 없습니다.")
            user_count = session.scalar(select(func.count()).select_from(User)) or 0
            admin_count = session.scalar(select(func.count()).select_from(User).where(User.is_system_admin == 1)) or 0
            if user_count == 1 and admin_count == 0:
                user.is_system_admin = 1
                user.revision += 1
                user.updated_at = utc_now_iso()
                target = session.scalar(select(SyncOutbox).where(
                    SyncOutbox.target_type == "USERS", SyncOutbox.target_id == "global",
                ))
                if target is None:
                    session.add(SyncOutbox(
                        id=str(uuid4()), target_type="USERS", target_id="global",
                        created_at=utc_now_iso(), retry_count=0,
                    ))
