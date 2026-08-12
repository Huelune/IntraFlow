from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from intraflow.models import AppMeta, Device, Part, Project, ProjectEditor, SyncOutbox, Unit, User, WorkItem
from intraflow.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from intraflow.timeutil import utc_now_iso


@dataclass(frozen=True, slots=True)
class Choice:
    id: str
    label: str


class AdministrationService:
    def __init__(self, session_factory: sessionmaker[Session], *, current_user_id: str) -> None:
        self.session_factory = session_factory
        self.current_user_id = current_user_id

    def current_permissions(self) -> tuple[bool, bool]:
        with self.session_factory() as session:
            user = self._current_user(session)
            editor = session.scalar(select(func.count()).select_from(ProjectEditor).where(
                ProjectEditor.user_id == user.id
            )) or 0
            return bool(user.is_system_admin), bool(editor)

    def can_manage_project(self, project_id: str) -> bool:
        with self.session_factory() as session:
            user = self._current_user(session)
            return bool(user.is_system_admin or session.get(ProjectEditor, (project_id, user.id)) is not None)

    def list_users(self) -> list[User]:
        with self.session_factory() as session:
            return list(session.scalars(select(User).order_by(User.user_code)))

    def create_user(
        self, user_code: str, display_name: str, *, is_system_admin: bool = False, is_active: bool = True,
    ) -> str:
        user_code, display_name = user_code.strip(), display_name.strip()
        if not user_code or not display_name:
            raise ValidationError("사용자 코드와 표시 이름은 필수입니다.")
        now, user_id = utc_now_iso(), str(uuid4())
        try:
            with self.session_factory.begin() as session:
                self._require_admin(session)
                session.add(User(id=user_id, user_code=user_code, display_name=display_name,
                                 is_system_admin=int(is_system_admin), is_active=int(is_active),
                                 created_at=now, updated_at=now, revision=1))
                self._mark_dirty(session, "USERS", "global")
        except IntegrityError as exc:
            raise ValidationError("이미 사용 중인 사용자 코드입니다.") from exc
        return user_id

    def update_user(
        self, user_id: str, user_code: str, display_name: str, *,
        is_system_admin: bool, is_active: bool,
    ) -> None:
        user_code, display_name = user_code.strip(), display_name.strip()
        if not user_code or not display_name:
            raise ValidationError("사용자 코드와 표시 이름은 필수입니다.")
        try:
            with self.session_factory.begin() as session:
                self._require_admin(session)
                user = session.get(User, user_id)
                if user is None:
                    raise NotFoundError("사용자를 찾을 수 없습니다.")
                if user.id == self.current_user_id and not is_active:
                    raise ValidationError("현재 사용자는 비활성화할 수 없습니다.")
                if user.is_system_admin and user.is_active and (not is_system_admin or not is_active):
                    active_admins = session.scalar(select(func.count()).select_from(User).where(
                        User.is_system_admin == 1, User.is_active == 1,
                    )) or 0
                    if active_admins <= 1:
                        raise ValidationError("마지막 활성 시스템 관리자의 권한을 해제할 수 없습니다.")
                if user.is_active and not is_active:
                    self._validate_editor_deactivation(session, user.id)
                user.user_code, user.display_name = user_code, display_name
                user.is_system_admin, user.is_active = int(is_system_admin), int(is_active)
                user.revision += 1
                user.updated_at = utc_now_iso()
                self._mark_dirty(session, "USERS", "global")
        except IntegrityError as exc:
            raise ValidationError("이미 사용 중인 사용자 코드입니다.") from exc

    def set_user_active(self, user_id: str, active: bool) -> None:
        with self.session_factory.begin() as session:
            self._require_admin(session)
            user = session.get(User, user_id)
            if user is None:
                raise NotFoundError("사용자를 찾을 수 없습니다.")
            if user.id == self.current_user_id and not active:
                raise ValidationError("현재 사용자는 비활성화할 수 없습니다.")
            if user.is_active and not active:
                self._validate_editor_deactivation(session, user.id)
            user.is_active, user.revision, user.updated_at = int(active), user.revision + 1, utc_now_iso()
            self._mark_dirty(session, "USERS", "global")

    def create_device(self, user_id: str, device_name: str, *, is_current: bool = False) -> str:
        if not device_name.strip():
            raise ValidationError("기기 이름은 필수입니다.")
        device_id = str(uuid4())
        with self.session_factory.begin() as session:
            self._require_admin(session)
            if session.get(User, user_id) is None:
                raise NotFoundError("사용자를 찾을 수 없습니다.")
            if is_current:
                for sibling in session.scalars(select(Device).where(Device.user_id == user_id)):
                    sibling.is_current = 0
            session.add(Device(id=device_id, user_id=user_id, device_name=device_name.strip(),
                               is_current=int(is_current), created_at=utc_now_iso()))
        return device_id

    def list_devices(self, user_id: str | None = None) -> list[Device]:
        statement = select(Device)
        if user_id:
            statement = statement.where(Device.user_id == user_id)
        with self.session_factory() as session:
            return list(session.scalars(statement.order_by(Device.user_id, Device.device_name)))

    def update_device(self, device_id: str, device_name: str, *, is_current: bool) -> None:
        if not device_name.strip():
            raise ValidationError("기기 이름은 필수입니다.")
        with self.session_factory.begin() as session:
            self._require_admin(session)
            device = session.get(Device, device_id)
            if device is None:
                raise NotFoundError("기기를 찾을 수 없습니다.")
            if is_current:
                for sibling in session.scalars(select(Device).where(Device.user_id == device.user_id)):
                    sibling.is_current = int(sibling.id == device.id)
            else:
                device.is_current = 0
            device.device_name = device_name.strip()

    def list_units(self) -> list[Unit]:
        with self.session_factory() as session:
            return list(session.scalars(select(Unit).order_by(Unit.sort_order, Unit.code)))

    def create_unit(
        self, code: str, display_name: str, *, sort_order: int = 0, is_active: bool = True,
    ) -> str:
        code, display_name = code.strip(), display_name.strip()
        if not code or not display_name:
            raise ValidationError("단위 코드와 표시 이름은 필수입니다.")
        unit_id = str(uuid4())
        try:
            with self.session_factory.begin() as session:
                self._require_admin(session)
                session.add(Unit(id=unit_id, code=code, display_name=display_name,
                                 is_active=int(is_active), sort_order=sort_order))
                self._increment_meta(session, "units_revision")
                self._mark_dirty(session, "UNITS", "global")
        except IntegrityError as exc:
            raise ValidationError("이미 사용 중인 단위 코드입니다.") from exc
        return unit_id

    def update_unit(
        self, unit_id: str, code: str, display_name: str, *, sort_order: int, is_active: bool,
    ) -> None:
        code, display_name = code.strip(), display_name.strip()
        if not code or not display_name:
            raise ValidationError("단위 코드와 표시 이름은 필수입니다.")
        try:
            with self.session_factory.begin() as session:
                self._require_admin(session)
                unit = session.get(Unit, unit_id)
                if unit is None:
                    raise NotFoundError("단위를 찾을 수 없습니다.")
                unit.code, unit.display_name, unit.sort_order = code, display_name, sort_order
                unit.is_active = int(is_active)
                self._increment_meta(session, "units_revision")
                self._mark_dirty(session, "UNITS", "global")
        except IntegrityError as exc:
            raise ValidationError("이미 사용 중인 단위 코드입니다.") from exc

    def set_unit_active(self, unit_id: str, active: bool) -> None:
        with self.session_factory.begin() as session:
            self._require_admin(session)
            unit = session.get(Unit, unit_id)
            if unit is None:
                raise NotFoundError("단위를 찾을 수 없습니다.")
            unit.is_active = int(active)
            self._increment_meta(session, "units_revision")
            self._mark_dirty(session, "UNITS", "global")

    def list_projects(self) -> list[Project]:
        with self.session_factory() as session:
            return list(session.scalars(select(Project).where(Project.is_deleted == 0).order_by(Project.name)))

    def create_project(self, name: str, planned_start: str | None = None, planned_end: str | None = None,
                       description: str | None = None, *, is_active: bool = True,
                       editor_user_id: str | None = None,
                       editor_user_ids: Iterable[str] | None = None) -> str:
        self._validate_period(name, planned_start, planned_end, "프로젝트")
        project_id, now = str(uuid4()), utc_now_iso()
        with self.session_factory.begin() as session:
            self._require_admin(session)
            session.add(Project(id=project_id, name=name.strip(), description=(description or "").strip() or None,
                                planned_start=planned_start, planned_end=planned_end,
                                status="ACTIVE" if is_active else "INACTIVE", revision=1,
                                is_deleted=0, created_at=now, updated_at=now, updated_by=self.current_user_id))
            editors = set(editor_user_ids) if editor_user_ids is not None else {self.current_user_id}
            if editor_user_id:
                editors.add(editor_user_id)
            self._validate_editor_users(session, editors, require_nonempty=is_active)
            for user_id in sorted(editors):
                session.add(ProjectEditor(project_id=project_id, user_id=user_id))
            self._mark_dirty(session, "PROJECT", project_id)
        return project_id

    def update_project(self, project_id: str, name: str, planned_start: str | None, planned_end: str | None,
                       description: str | None = None, *, allow_child_conflicts: bool = False,
                       is_active: bool | None = None, editor_user_id: str | None = None,
                       editor_user_ids: Iterable[str] | None = None) -> None:
        self._validate_period(name, planned_start, planned_end, "프로젝트")
        with self.session_factory.begin() as session:
            self._require_project_manager(session, project_id)
            project = session.get(Project, project_id)
            if project is None or project.is_deleted:
                raise NotFoundError("프로젝트를 찾을 수 없습니다.")
            conflicts = list(session.scalars(select(Part).where(
                Part.project_id == project_id, Part.is_deleted == 0,
                ((Part.planned_start < planned_start) | (Part.planned_end > planned_end)))))
            if conflicts and not allow_child_conflicts:
                details = [
                    f"{project.name} > {part.name} ({part.planned_start} ~ {part.planned_end})"
                    for part in conflicts[:5]
                ]
                raise ValidationError("새 기간을 벗어나는 파트가 있습니다:\n" + "\n".join(details))
            project.name, project.description = name.strip(), (description or "").strip() or None
            project.planned_start, project.planned_end = planned_start, planned_end
            if is_active is not None:
                project.status = "ACTIVE" if is_active else "INACTIVE"
            requested_editors = set(editor_user_ids) if editor_user_ids is not None else None
            if editor_user_id:
                requested_editors = requested_editors or {
                    value.user_id for value in session.scalars(
                        select(ProjectEditor).where(ProjectEditor.project_id == project_id)
                    )
                }
                requested_editors.add(editor_user_id)
            if requested_editors is not None:
                self._require_admin(session)
                self._replace_project_editors(session, project_id, requested_editors)
            self._touch_project(session, project_id)

    def set_project_active(self, project_id: str, active: bool) -> None:
        with self.session_factory.begin() as session:
            self._require_project_manager(session, project_id)
            project = session.get(Project, project_id)
            if project is None or project.is_deleted:
                raise NotFoundError("프로젝트를 찾을 수 없습니다.")
            if active:
                editors = {value.user_id for value in session.scalars(
                    select(ProjectEditor).where(ProjectEditor.project_id == project_id)
                )}
                self._validate_editor_users(session, editors)
            project.status = "ACTIVE" if active else "INACTIVE"
            self._touch_project(session, project_id)

    def add_project_editor(self, project_id: str, user_id: str) -> None:
        with self.session_factory() as session:
            current = {value.user_id for value in session.scalars(
                select(ProjectEditor).where(ProjectEditor.project_id == project_id)
            )}
        if user_id in current:
            raise ValidationError("이미 프로젝트 편집자로 등록된 사용자입니다.")
        self.replace_project_editors(project_id, current | {user_id})

    def list_project_editors(self, project_id: str) -> list[User]:
        with self.session_factory() as session:
            return list(session.scalars(
                select(User).join(ProjectEditor, ProjectEditor.user_id == User.id)
                .where(ProjectEditor.project_id == project_id)
                .order_by(User.display_name, User.user_code)
            ))

    def replace_project_editors(self, project_id: str, user_ids: Iterable[str]) -> None:
        with self.session_factory.begin() as session:
            self._require_admin(session)
            project = session.get(Project, project_id)
            if project is None or project.is_deleted:
                raise NotFoundError("프로젝트를 찾을 수 없습니다.")
            self._replace_project_editors(session, project_id, set(user_ids))
            self._touch_project(session, project_id)

    def list_parts(self, project_id: str | None = None) -> list[Part]:
        statement = select(Part).where(Part.is_deleted == 0)
        if project_id:
            statement = statement.where(Part.project_id == project_id)
        with self.session_factory() as session:
            return list(session.scalars(statement.order_by(Part.project_id, Part.sort_order, Part.name)))

    def create_part(self, project_id: str, name: str, weight: float, planned_start: str | None = None,
                    planned_end: str | None = None, *, is_active: bool = True) -> str:
        self._validate_period(name, planned_start, planned_end, "파트")
        self._validate_weight(weight)
        part_id, now = str(uuid4()), utc_now_iso()
        with self.session_factory.begin() as session:
            self._require_project_manager(session, project_id)
            project = session.get(Project, project_id)
            if project is None or project.is_deleted:
                raise NotFoundError("프로젝트를 찾을 수 없습니다.")
            self._validate_within(planned_start, planned_end, project.planned_start, project.planned_end, "파트")
            session.add(Part(id=part_id, project_id=project_id, name=name.strip(), weight=weight,
                             planned_start=planned_start, planned_end=planned_end, sort_order=0,
                             is_active=int(is_active), is_deleted=0, created_at=now, updated_at=now))
            self._touch_project(session, project_id)
        return part_id

    def update_part(self, part_id: str, name: str, weight: float, planned_start: str | None,
                    planned_end: str | None, *, allow_child_conflicts: bool = False,
                    is_active: bool | None = None) -> None:
        self._validate_period(name, planned_start, planned_end, "파트")
        self._validate_weight(weight)
        with self.session_factory.begin() as session:
            part = session.get(Part, part_id)
            if part is None or part.is_deleted:
                raise NotFoundError("파트를 찾을 수 없습니다.")
            self._require_project_manager(session, part.project_id)
            project = session.get(Project, part.project_id)
            self._validate_within(planned_start, planned_end, project.planned_start if project else None,
                                  project.planned_end if project else None, "파트")
            conflicts = list(session.execute(
                select(WorkItem, User.display_name)
                .join(User, WorkItem.owner_user_id == User.id)
                .where(
                    WorkItem.part_id == part_id, WorkItem.is_deleted == 0,
                    ((WorkItem.planned_start < planned_start) | (WorkItem.planned_end > planned_end)),
                )
            ))
            if conflicts and not allow_child_conflicts:
                details = [
                    f"{project.name} > {part.name} > {item.name} / 소유자 {owner} "
                    f"({item.planned_start} ~ {item.planned_end})"
                    for item, owner in conflicts[:5]
                ]
                raise ValidationError("새 기간을 벗어나는 업무가 있습니다:\n" + "\n".join(details))
            part.name, part.weight, part.planned_start, part.planned_end = name.strip(), weight, planned_start, planned_end
            if is_active is not None:
                part.is_active = int(is_active)
            part.updated_at = utc_now_iso()
            self._touch_project(session, part.project_id)

    def set_part_active(self, part_id: str, active: bool) -> None:
        with self.session_factory.begin() as session:
            part = session.get(Part, part_id)
            if part is None or part.is_deleted:
                raise NotFoundError("파트를 찾을 수 없습니다.")
            self._require_project_manager(session, part.project_id)
            part.is_active, part.updated_at = int(active), utc_now_iso()
            self._touch_project(session, part.project_id)

    def choices(self) -> dict[str, list[Choice]]:
        with self.session_factory() as session:
            return {
                "users": [Choice(x.id, x.display_name) for x in session.scalars(select(User).where(User.is_active == 1).order_by(User.display_name))],
                "units": [Choice(x.id, x.display_name) for x in session.scalars(select(Unit).where(Unit.is_active == 1).order_by(Unit.sort_order, Unit.code))],
                "projects": [Choice(x.id, x.name) for x in session.scalars(select(Project).where(Project.is_deleted == 0).order_by(Project.name))],
                "parts": [Choice(x.id, x.name) for x in session.scalars(select(Part).where(Part.is_deleted == 0).order_by(Part.name))],
            }

    def _current_user(self, session: Session) -> User:
        user = session.get(User, self.current_user_id)
        if user is None or not user.is_active:
            raise PermissionDeniedError("현재 사용자가 없거나 비활성 상태입니다.")
        return user

    def _require_admin(self, session: Session) -> User:
        user = self._current_user(session)
        if not user.is_system_admin:
            raise PermissionDeniedError("시스템 관리자 권한이 필요합니다.")
        return user

    def _require_project_manager(self, session: Session, project_id: str) -> None:
        user = self._current_user(session)
        if not user.is_system_admin and session.get(ProjectEditor, (project_id, user.id)) is None:
            raise PermissionDeniedError("프로젝트 관리자 또는 편집자 권한이 필요합니다.")

    @staticmethod
    def _validate_period(name: str, start: str | None, end: str | None, label: str) -> None:
        if not name.strip():
            raise ValidationError(f"{label} 이름은 필수입니다.")
        if not start or not end:
            raise ValidationError(f"{label} 시작일과 종료일은 필수입니다.")
        if len(start) != 10 or len(end) != 10 or end < start:
            raise ValidationError("올바른 시작일과 종료일을 선택하세요.")

    @staticmethod
    def _validate_within(start: str, end: str, parent_start: str | None, parent_end: str | None, label: str) -> None:
        if (parent_start and start < parent_start) or (parent_end and end > parent_end):
            raise ValidationError(f"{label} 일정은 상위 기간 안에 있어야 합니다.")

    @staticmethod
    def _validate_weight(weight: float) -> None:
        if not 0 < weight <= 1:
            raise ValidationError("가중치는 0보다 크고 1 이하여야 합니다.")

    def _touch_project(self, session: Session, project_id: str) -> None:
        project = session.get(Project, project_id)
        if project is None:
            raise NotFoundError("프로젝트를 찾을 수 없습니다.")
        project.revision, project.updated_at, project.updated_by = project.revision + 1, utc_now_iso(), self.current_user_id
        self._mark_dirty(session, "PROJECT", project_id)

    @staticmethod
    def _validate_editor_users(
        session: Session, user_ids: set[str], *, require_nonempty: bool = True,
    ) -> None:
        if not user_ids and require_nonempty:
            raise ValidationError("프로젝트에는 활성 편집자가 한 명 이상 필요합니다.")
        if not user_ids:
            return
        users = {user.id: user for user in session.scalars(select(User).where(User.id.in_(user_ids)))}
        if set(users) != user_ids or any(not user.is_active for user in users.values()):
            raise ValidationError("활성 사용자만 프로젝트 편집자로 지정할 수 있습니다.")

    def _replace_project_editors(self, session: Session, project_id: str, user_ids: set[str]) -> None:
        project = session.get(Project, project_id)
        self._validate_editor_users(
            session, user_ids, require_nonempty=bool(project and project.status == "ACTIVE"),
        )
        existing = {value.user_id: value for value in session.scalars(
            select(ProjectEditor).where(ProjectEditor.project_id == project_id)
        )}
        for removed_id in set(existing) - user_ids:
            session.delete(existing[removed_id])
        for added_id in user_ids - set(existing):
            session.add(ProjectEditor(project_id=project_id, user_id=added_id))

    @staticmethod
    def _validate_editor_deactivation(session: Session, user_id: str) -> None:
        projects = list(session.scalars(
            select(Project).join(ProjectEditor, ProjectEditor.project_id == Project.id)
            .where(ProjectEditor.user_id == user_id, Project.status == "ACTIVE", Project.is_deleted == 0)
        ))
        for project in projects:
            active_editors = session.scalar(
                select(func.count()).select_from(ProjectEditor).join(User, ProjectEditor.user_id == User.id)
                .where(ProjectEditor.project_id == project.id, User.is_active == 1, User.id != user_id)
            ) or 0
            if active_editors == 0:
                raise ValidationError(
                    f"활성 프로젝트 '{project.name}'의 마지막 편집자는 비활성화할 수 없습니다.",
                )

    @staticmethod
    def _increment_meta(session: Session, key: str) -> int:
        value = session.get(AppMeta, key)
        if value is None:
            value = AppMeta(key=key, value="1")
            session.add(value)
            return 1
        revision = int(value.value or "0") + 1
        value.value = str(revision)
        return revision

    @staticmethod
    def _mark_dirty(session: Session, target_type: str, target_id: str) -> None:
        target = session.scalar(select(SyncOutbox).where(
            SyncOutbox.target_type == target_type, SyncOutbox.target_id == target_id))
        if target is None:
            session.add(SyncOutbox(id=str(uuid4()), target_type=target_type, target_id=target_id,
                                   created_at=utc_now_iso(), retry_count=0))
        else:
            target.retry_count, target.next_retry_at, target.last_error = 0, None, None
