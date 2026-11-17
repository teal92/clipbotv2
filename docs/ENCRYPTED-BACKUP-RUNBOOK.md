# Encrypted private database backup

This manual operator tool reads `/var/data/clipbot.db` using SQLite read-only mode,
copies a consistent snapshot to a disposable private server directory, validates
integrity and every table's content, and encrypts it with AES-256-GCM before any
customer data leaves Render. It never changes the live database. No cloud service,
paid service, schedule, pruning, or live restoration is provided.

The uncompressed archive has a strict 32 MiB limit. The encrypted file contains
the database, authenticated schema/table hashes, and only the explicit recovery
environment names in `ops/encrypted_backup.py`. These include OAuth application
credentials, token encryption key, Stripe configuration, SMTP settings, admin
account ID, AI key/budgets, customer access settings, and companion references.
If the operator credential is file-based, only `/var/data/clipbot-c2.key` is read;
custom paths are rejected. Unrelated environment secrets are excluded. OAuth
customer credentials in the database remain encrypted by their existing vault key.

## Credentials and locations

- SSH private identity: existing `clipbot-render-migration` file in the private
  operator work directory; not copied into the backup.
- Pinned server host key: existing `render-known-hosts` file in that directory.
- Recovery master key: `%LOCALAPPDATA%\ClipBotRecovery\master.dpapi`, separate
  from backups. AES key is protected by Windows DPAPI for the current Windows user;
  directory/file ACLs grant only that user. There is no production plaintext mode.
- Encrypted output: `C:\Users\<you>\Documents\ClipBotBackups\clipbot-*.cbk`.
  Output names are unique and an existing file can never be replaced.
- Server recovery settings: hosting environment plus the fixed C2 key path above.
  Settings are saved only inside authenticated encryption, never printed.

Run from the isolated project snapshot in PowerShell. The commands contain paths
and identifiers only, never a credential value:

```powershell
$backupPython = 'C:\Users\<you>\Desktop\clipbot-saas\.venv\Scripts\python.exe'
$operatorDirectory = 'C:\path\to\operator-files'
& $backupPython -m ops.encrypted_backup backup --destination 'C:\Users\<you>\Documents\ClipBotBackups' --identity "$operatorDirectory\clipbot-render-migration" --known-hosts "$operatorDirectory\render-known-hosts" --target 'YOUR-RENDER-SERVICE-ID@ssh.oregon.render.com'
```

The first authorized run creates a random master key protected with DPAPI. A fresh
random session key is sent exclusively over pinned SSH stdin; it is never placed
in process arguments or environment variables. The encrypted server response is
wrapped locally under the master key. A private temporary recovery drill must
pass before the final encrypted file is promoted atomically. Success prints only
booleans, table count, encrypted size, and the generated filename. Errors print a
fixed generic message; SSH diagnostics and credential values are discarded.

## Offline recovery drill

Choose one saved filename from the backup command's safe output. Substitute that
filename below; the example placeholder does not denote a real backup:

```powershell
& $backupPython -m ops.encrypted_backup drill --backup-file 'C:\Users\<you>\Documents\ClipBotBackups\YOUR-SAVED-FILENAME.cbk'
```

This checks both AES authentication layers, archive format/size/member hashes,
SQLite integrity/foreign keys, schema hashes and every table's row counts/content
hashes. The database is decrypted only to a private temporary directory which is
removed after the drill. Recovery settings remain in memory. It reports credential
presence as booleans and never prints a customer row, table hash, or secret.

Actual restoration remains a separate manual maintenance operation. There is no
command or endpoint that can overwrite the live database. Before any real restore,
pause writes, identify the correct backup/revision, preserve the current database,
decrypt only into a private isolated location, restore hosting credentials from
`recovery.json`, and validate the recovered service with public signup and live
billing disabled until an explicit release review. Existing encrypted token data
requires the matching `CLIPBOT_TOKEN_ENCRYPTION_KEY`.

## Recovery boundary

This protects against loss of the Render service/disk while the same Windows user
profile remains available. DPAPI key recovery depends on that user's Windows
profile. Losing both this PC/profile and its backups loses this recovery path;
the tool does not claim disaster recovery for loss of both machines. Customer
uploads/media, infrastructure/DNS/provider app setup, and SSH credentials are not
included. Keep the protected master file; never rotate/delete it or move a key
between Windows profiles without a separately approved recovery procedure.

No recurrence or cleanup is enabled. Retain existing backups until the owner
explicitly requests a retention policy. Synthetic verification:

```powershell
& $backupPython -m pytest tests/test_encrypted_backup.py -q --basetemp=.test-temp-backup-verification
```
