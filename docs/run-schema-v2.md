# Forge3D run schema v2

Every run directory contains one atomically written `run.json`. User runs are outside source control
at `%USERPROFILE%\Documents\Forge3D\runs\<timestamp>-<slug>-<id>`.

## Required v2 fields

- `schema_version`: `2`
- `run_id`: stable UUID
- `name`, `command`, and `workflow_route`
- `status`, `created_at`, `updated_at`, and optional `completed_at`
- `prompt`, copied `inputs`, and selected `settings`
- ordered `steps`
- compatibility `outputs` map
- relative `artifacts` descriptors
- `validation` results and detected `tools`
- `codex.thread_id` and ordered `codex.turn_ids`
- persistent `transcript` and optional `failure`

An artifact descriptor contains `name`, relative `path`, `media_type`, `preview_role`,
`workflow_route`, and when available `size_bytes` and `sha256`. Image sequences additionally contain
ordered relative `frames`.

Supported preview roles are `primary-image`, `image`, `animation`, `image-sequence`, `model`,
`gaussian-splat`, `validation`, `text`, and `metadata`. Paths are never allowed to escape the run
directory. Symlink artifacts are not served.

## Schema v1 compatibility

The Python and Electron loaders accept schema versions 1 and 2. A v1 run remains unchanged on disk;
for display, the Electron run store derives contained artifact descriptors from its legacy `outputs`
map. Unknown schemas are rejected. Disposable historical test runs are not migrated.

## Status and recovery

Python workflows retain detailed domain states such as `awaiting_blender_review` or
`awaiting_codex`. The desktop orchestration uses prepared, launching, running, cancelling, completed,
interrupted, and failed. On process restart, transient desktop states become interrupted with a
recovery message; stored thread and turn IDs allow an explicit continuation.

## File actions

Duplicate creates a new run version and copies only declared attachments. Archive moves the run into
the hidden archive inside the runs root and keeps it browsable. Trash uses the Windows Recycle Bin.
These operations are run-scoped and do not accept arbitrary destination paths.