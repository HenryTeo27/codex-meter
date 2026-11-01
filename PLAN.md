# Codex Meter plan and completion notes

## Selectable speed windows — 2026-11-01

1. Save independent 4-hour, 1-day and 14-day switches. Default to 4 hours and 1 day, including existing installations without this setting.
2. Capture enabled accounts and speed windows together at refresh start. Manual and automatic refresh use this same selection. Changes during a scan apply to the next scan.
3. Parse each enabled account once. Read only logs within the longest selected window. Compute only selected reports; skip the speed worker and tool download when none are selected.
4. Hide disabled tables without rebuilding the page. Keep cached results until a selected window refreshes. Preserve disabled account results without reading their logs or querying their account.
5. Verify saved switches, worker arguments, exact rolling cutoffs, all-off behavior and changes between consecutive refreshes with isolated backend and withdrawn-window tests.
6. Update English usage documentation, build the Windows package, verify it without opening desktop windows, and publish the release.

Implementation and verification:

- Added saved window checkboxes and a default 4-hour / 1-day selection. Both refresh paths capture account and window choices at scan start.
- Kept one parse per enabled account. The longest checked window sets the log-file cutoff. No checked windows means no speed process or tool download.
- Preserved the latest cached results for disabled accounts and unchecked windows. New empty results replace old results for refreshed windows.
- Passed the isolated backend and withdrawn-window suite, including selection changes during a refresh, all-off behavior, rolling cutoffs and account skips.
- A real scan of two enabled local accounts returned both default windows in 18.78 seconds. No desktop window was opened.
- Built v1.1.6. The packaged runtime, two-process quit/reopen check, automatic scheduling check and update archive check passed.

- [x] Native compact Windows window, tray open/refresh/quit, single-instance reopening.
- [x] Remaining Codex allowance; current-month and all-time tokens and USD estimates.
- [x] Configurable all-time reserve adjustment; token delta from last successful usage scan.
- [x] 1-day and 14-day Selected history speeds, hover details and colored ratios.
- [x] Manual or 2/4/6/8/12-hour refresh; background workers, command timeouts and retained previous results.
- [x] Transparent multi-resolution Windows icon.
- [x] Source and dependency credits below the data, using natural mouse-wheel scrolling with no visible scrollbar.
- [x] Latest-tool checks with a last-working speed-script fallback; no separate speed-tool installation required.
- [x] Windows executable ZIP, desktop and Start menu shortcuts, source installer and MIT license.
- [x] README with quick download, Codex-assisted source installation, data semantics and limitations.
- [x] Verify packaged workers, real speed and account data, desktop installation and five-launch single-instance behavior.

Final delivery: publish the source commit and Windows release to the public GitHub repository.

Only the latest snapshot and settings are retained, plus the working speed script. Temporary sample outputs and caches are removed after scans. npm retains its own package cache. Resource use during scans depends on log size. No long-term power benchmark has been performed.

## v1.0.1 refresh repair

- Include the certificate data required by the Codex-patched Python runtime. Keep TLS verification enabled.
- Run usage, limits and speed concurrently and display each result as it arrives.
- Parse recent speed logs once; use the upstream statistics for both rolling windows. Use orjson only for JSON decoding.
- Distinguish successful data refresh with tool fallback from a failed source. Expose current failure details on hover.
- Validate the packaged executable against real data, not only mocked source tests. Recorded diagnostic times: limits 2.78s, speed 18.36s, usage 42.59s. Times depend on the logs and network.
- On the first launch after a version change, refresh once to verify and replace previous results.

## v1.0.2 resource optimization

- Lazy GUI imports for worker and duplicate launches; small ICO images for tray/header.
- One isolated speed worker; defer hidden redraws and reduce active-only polling.
- Track and terminate owned scan process trees on quit.
- Verified successful real packaged scans, hidden restoration and 10 regression tests.
- Recorded visible/tray idle samples and sampled refresh-tree resource use in docs/performance.md. No hardware power measurement was performed.

## v1.0.18 refresh and app updates

- Keep the three data sources concurrent. Update only changed widgets, and defer hidden or minimized window updates until restore.
- Add 30-minute and 1-hour refresh choices. Default new installations to 2 hours and preserve existing settings.
- Check GitHub for a newer stable app release in the background. Verify its release digest and run a hidden startup check before installation.
- Apply ready updates when the app is idle in the tray, or when the user quits. Keep settings and the latest snapshot. Restore the previous app if the replacement cannot start, and wait before retrying a failed update.
- Keep development and portable runs separate from the installed app's updater. Test update downloads, path safety, retries and rollback with isolated files and hidden processes.

## v1.1.5 repository migration and update recovery

- Move the canonical repository to codex-meter. Keep the old repository and historical release assets as compatibility endpoints.
- Preserve strict release URL, SHA-256 and startup checks for both repository addresses.
- Check every 6 hours and during refresh after a 1-hour minimum.
- Preserve the verified archive across restarts and recheck it locally before installation.
- Resume pending updates before the next app window or once at Windows sign-in. Preserve explicit Quit behavior, settings and latest results.
