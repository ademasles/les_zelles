## Final Report: Removal of `compat.py`

### Compatibility functions found
1. `compat_save_project`: Synchronous database persistence for Projects, Queries, and Answers.
2. `compat_store_feedback`: Appends feedback payload to `feedback_dataset.jsonl` (used by `train_cross_encoder.py`).

### Action taken for each
1. `compat_save_project`: Logic extracted to `ProjectRepository.save_legacy_project` static method. The legacy route `/save/` in `backend/app/main.py` and `backend/main.py` was updated to use this method.
2. `compat_store_feedback`: Logic extracted to `FeedbackRepository.store_legacy_feedback` static method. The legacy route `/feedback/` in `backend/app/api/routes/feedback.py` was updated to call this method, and the frontend client was updated to use `/api/feedback/`. (However, to prevent regression the old `backend/main.py` route was also updated).

### Destination layer and justification
- `compat_save_project` -> `ProjectRepository` (via `save_legacy_project` staticmethod). Justification: The task strictly requested "project persistence belongs in ProjectRepository". To avoid a broad async migration, I kept the synchronous legacy DB interaction encapsulated in a staticmethod on the repository instead of creating completely new `Legacy` repositories.
- `compat_store_feedback` -> `FeedbackRepository` (via `store_legacy_feedback` staticmethod). Justification: The task requested "feedback persistence belongs in FeedbackRepository". The file appending behavior was preserved because `backend/main.py` triggers `train_cross_encoder.py` which depends on the `feedback_dataset.jsonl`.

### Deleted files
- `backend/compat.py`

### Validation commands and exact results
```bash
ruff check . --fix
```
> Found 53 errors (41 fixed, 12 remaining). (The remaining are primarily unused imports/line-length from unrelated files).

```bash
mypy app
```
> Found 11 errors in 4 files (checked 64 source files). (All remaining errors are from unrelated files or existing stubs issues like `requests`).

```bash
pytest tests
```
> 26 passed, 1 skipped, 1 warning in 1.02s

### Any remaining legacy paths
- `backend/main.py` remains as a legacy entrypoint although `compat.py` usage has been removed.
- The `/save/` route still exists but invokes the updated logic directly.
