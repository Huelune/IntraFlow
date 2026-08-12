from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.setup_service import SetupService
from intraflow.services.workstation_service import WorkstationService


def test_current_pc_name_is_managed_locally(session_factory: sessionmaker[Session]) -> None:
    identity = SetupService(session_factory).provision("owner", "Owner", "PC-1")
    service = WorkstationService(
        session_factory, current_user_id=identity.user_id, current_device_id=identity.device_id,
    )
    service.update_device_name("업무용 PC")
    info = service.get_current()
    assert info.user_code == "owner"
    assert info.device_name == "업무용 PC"
