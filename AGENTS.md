# IntraFlow Codex Instructions

## Product rule

IntraFlow is an offline-first desktop application for a small trusted internal team. It must continue to allow local work updates when the NAS is unavailable.

## Architecture rules

- UI must never write SQLite directly.
- UI calls Service.
- Service calls Repository / SQLAlchemy Session.
- Business Service must never write NAS files directly.
- NAS I/O belongs to `intraflow.sync`.
- Local SQLite is never placed on NAS.
- Do not implement whole-DB file copying or DB merge synchronization.
- Shared synchronization uses JSON snapshots.
- A user writes only their own public snapshot.
- Other users' shared progress/calendar data is read-only in the application layer.
- System Admin and Project Editor are separate permissions.
- System Admin does not gain permission to edit another user's progress or schedule.

## Data rules

- Shared entity IDs are UUIDv4 strings.
- Store timestamps as UTC ISO-8601 strings.
- Date-only scheduling fields use `YYYY-MM-DD`.
- Progress percentages are derived, never persisted as source data.
- Work calendar entries are derived from AssignmentProgress schedule dates and are not duplicated into CalendarEvent.
- PersonalNote and PRIVATE CalendarEvent are local-only.
- Assignment with progress history is cancelled instead of physically deleted.
- Shared definitions prefer tombstones (`is_deleted`) over physical deletes.
- No `ON DELETE CASCADE` for shared work/progress entities.

## Progress transaction

A progress update must be atomic:

1. validate assignment
2. update/create AssignmentProgress
3. append ProgressHistory
4. mark USER_PUBLIC target dirty in SyncOutbox
5. commit

A NAS failure must never roll back a successful local progress transaction.

## Scope guard

Do not add these to v1 unless explicitly requested:

- web/mobile version
- central DB/app server
- chat/comments
- attachments
- AI delay prediction
- complex capacity/workload math
- task dependency engine
- drag-and-drop Gantt editing
- OS/email push notifications
