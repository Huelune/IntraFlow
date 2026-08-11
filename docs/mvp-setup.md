# IntraFlow MVP setup

## Install

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

## Configure the workstation

Copy `intraflow.local.toml.example` to `intraflow.local.toml`. An administrator must provision UUIDv4 values for `current_user_id` and `current_device_id`.

Set `nas_root_path` to the already-mounted network drive or UNC path used for snapshot sharing. Do not place the local SQLite database on that path.

## Run

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m intraflow.main
```

The MVP shows the configured user's active assignments. Applying progress always commits locally first; NAS synchronization is a separate retryable action.
