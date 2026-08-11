# IntraFlow MVP setup

## Install

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

## Configure the workstation

The first app launch opens a setup dialog. Enter the user code, display name, optional PC name, and the already-mounted NAS path. IntraFlow creates the UUIDv4 user/device records, grants the first user system-administrator access, and writes `intraflow.local.toml` automatically.

For manual provisioning, copy `intraflow.local.toml.example` and set the IDs to records that already exist in the local database. Do not place the local SQLite database on the NAS path.

## Run

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m intraflow.main
```

Create data in this order from the management tab: user, unit, project, part, work item, and assignment. The assigned work then appears in `My Work`. Applying progress always commits locally first; NAS synchronization is a separate retryable action in the synchronization tab.
