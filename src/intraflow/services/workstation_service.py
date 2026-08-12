from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import Device, User
from intraflow.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from intraflow.timeutil import utc_now_iso


@dataclass(frozen=True, slots=True)
class WorkstationInfo:
    user_id: str
    user_code: str
    display_name: str
    device_id: str
    device_name: str


class WorkstationService:
    """Manage the current PC's local identity without exposing devices as shared admin data."""

    def __init__(
        self, session_factory: sessionmaker[Session], *, current_user_id: str, current_device_id: str,
    ) -> None:
        self.session_factory = session_factory
        self.current_user_id = current_user_id
        self.current_device_id = current_device_id

    def get_current(self) -> WorkstationInfo:
        with self.session_factory() as session:
            user = session.get(User, self.current_user_id)
            device = session.get(Device, self.current_device_id)
            if user is None or device is None:
                raise NotFoundError("현재 사용자 또는 PC 정보를 찾을 수 없습니다.")
            if device.user_id != user.id:
                raise PermissionDeniedError("현재 PC가 로그인 사용자에게 등록되어 있지 않습니다.")
            return WorkstationInfo(
                user.id, user.user_code, user.display_name, device.id, device.device_name or "",
            )

    def update_device_name(self, device_name: str) -> None:
        name = device_name.strip()
        if not name:
            raise ValidationError("PC 이름은 필수입니다.")
        with self.session_factory.begin() as session:
            device = session.get(Device, self.current_device_id)
            if device is None:
                raise NotFoundError("현재 PC 정보를 찾을 수 없습니다.")
            if device.user_id != self.current_user_id:
                raise PermissionDeniedError("현재 PC 이름만 수정할 수 있습니다.")
            device.device_name = name
            device.is_current = 1
            device.last_seen_at = utc_now_iso()
