# Weekly encrypted recovery backups

The owner approved weekly backups on Monday night with a manual option in the private C2 ClipBot dashboard. The installed current-user Windows task is `YourCompany-ClipBot-Encrypted-Backup`, next scheduled for Monday October 19, 2026 at 8 PM Eastern. It requires this computer on, online and the owner signed in. It does not wake the PC. Missed runs are eligible when available; actual future execution has not yet occurred.

The task uses the existing verified Python environment and exactly `-m ops.backup_job` in this checkout, with InteractiveToken/least privilege, no stored Windows password, one instance, and a ten-minute execution bound. It reads only the existing approved Render service over pinned private SSH and saves verified encrypted archives in `C:/Users/<you>/Documents/ClipBotBackups`. No paid service, automatic pruning, plaintext database export or live restore was added.

Both scheduled and C2 manual requests execute the same fixed job. The job requires an existing protected master key, preserves it, rejects foreign service targets and linked paths, holds an OS file lock, bounds its child to 120 seconds, independently decrypts/integrity-checks the encrypted output, and atomically records only safe status metadata. The existing remote snapshot watchdog is 90 seconds. A failure retains the previous verified backup, records only a stage/allowlisted exception class locally, and never logs raw exception details or starts an automatic retry. Windows child helpers run without visible console windows.

`backup-location.json` in the private backup folder records exactly two absolute local file locations for the protected key and fixed connection configuration. It contains no key value. Codex's packaged Windows AppData redirection meant a background task could not use the logical app-data path; Windows file-handle resolution established the existing physical files, and their bytes matched exactly before recording those paths. The key was never regenerated or replaced. Missing/malformed location metadata fails closed.

Private C2 has a ClipBot-only Backups tab, fresh owner password/MFA authorization and exact same-origin checks for manual runs, a one-per-minute action limit, and strict fixed-task/action/principal matching before Run. It exposes no task arguments, keys, SSH access or backup content to the browser. It does not treat an accepted request or old success as completion. Stale running receipts become unconfirmed after 180 seconds, permitting explicit reconciliation/retry with OS duplicate protection. See the C2 repository's `docs/CLIPBOT-BACKUPS.md` for owner instructions.

## Evidence

- The actual installed task completed successfully and independently verified all 58 current tables in `clipbot-20261015T120957Z-7aedec08.cbk` (3,082,794 encrypted bytes).
- Task Scheduler reported result 0 and the next local run at October 19, 20:00. Its effective privilege was Limited and logon was Interactive. Windows omits the default least-privilege XML field; explicit elevated values remain rejected.
- Backup/job/portable recovery regression: 31 tests passed. New cases were observed failing before implementation: background console suppression, secret-free failure stages and explicit location selection across session environments.
- C2: 57 Python tests and six frontend suites passed. Read-only independent review found no important issues in the job, installer and C2 security boundary.
- The second-computer recovery drill is still pending. Weekly scheduling does not replace the portable recovery export and separate passphrase, nor pre-deployment snapshots. A weekly interval can leave up to a week of new changes absent from the latest scheduled copy.

The ClipBot server runtime remains the separately verified private build ceb460f. These local operation changes do not open signup, live billing, customer AI or public installer release.
