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
