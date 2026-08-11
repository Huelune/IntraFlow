from sqlalchemy.orm import Session, sessionmaker

from intraflow.services.administration_service import AdministrationService
from intraflow.services.setup_service import SetupService
from intraflow.services.work_service import WorkService


def build_workflow(session_factory: sessionmaker[Session], *, code: str = "owner"):
    identity = SetupService(session_factory).provision(code, code.title(), f"{code.upper()}-PC")
    admin = AdministrationService(session_factory, current_user_id=identity.user_id)
    unit_id = admin.create_unit(f"EA-{code}", "개")
    project_id = admin.create_project("프로젝트", "2026-08-01", "2026-08-31", "설명")
    part_id = admin.create_part(project_id, "파트", 1.0, "2026-08-01", "2026-08-31")
    work = WorkService(session_factory, current_user_id=identity.user_id)
    item_id = work.create_my_work_item(
        part_id, "업무", "업무 설명", 10, unit_id, 1.0, "2026-08-02", "2026-08-20",
    )
    item = work.get_my_work_item(item_id)
    return identity, admin, work, project_id, part_id, item
