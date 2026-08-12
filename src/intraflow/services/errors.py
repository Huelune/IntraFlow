class IntraFlowError(Exception):
    """Base application error."""


class NotFoundError(IntraFlowError):
    pass


class PermissionDeniedError(IntraFlowError):
    pass


class ValidationError(IntraFlowError):
    pass


class SyncError(IntraFlowError):
    pass


class RevisionConflictError(SyncError):
    pass


class UserPublicConflictError(RevisionConflictError):
    def __init__(self, user_id: str, known_revision: int, remote_revision: int) -> None:
        self.user_id = user_id
        self.known_revision = known_revision
        self.remote_revision = remote_revision
        super().__init__(
            "다른 PC에서 내 업무가 변경되었습니다. Push 전에 사용자 업무 충돌을 해결하세요. "
            f"(로컬 기준 {known_revision}, NAS {remote_revision})"
        )
