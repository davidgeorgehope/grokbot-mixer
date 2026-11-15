On 2026-11-14 (America/New_York) the following *completed, inactive* mix
output folders were moved to Google Drive to free box disk. They had not
been modified in the last 24 hours and no process had them open.

Active mix 09 work (src, src2, deliver, jobs, visuals, mix09, eval, etc.)
was left in place.

  local folder     Drive path (rclone remote gdrive:)
  --------------   ----------------------------------------------------------
  mixes/mix06      gdrive:box-archive/2026-11-14/workspace/mixes/mix06
                   89 files, 702,417,072 bytes (verified rclone check --checksum)
  mixes/mix07      gdrive:box-archive/2026-11-14/workspace/mixes/mix07
                   99 files, 2,203,631,502 bytes (verified rclone check --checksum)
  mixes/viz06v3    gdrive:box-archive/2026-11-14/workspace/mixes/viz06v3
                   16 files, 417,564,670 bytes (verified rclone check --checksum)
  mixes/ai         gdrive:box-archive/2026-11-14/workspace/mixes/ai
                   8 files, 61,597,836 bytes (verified rclone check --checksum)
  mixes/ev2        gdrive:box-archive/2026-11-14/workspace/mixes/ev2
                   14 files, 22,132,747 bytes (verified rclone check --checksum)

Each of those local folders now contains only a README.txt pointing here.

Restore one folder:
  ~/bin/rclone copy --checksum gdrive:box-archive/2026-11-14/workspace/mixes/mix07 /workspace/mixes/mix07
