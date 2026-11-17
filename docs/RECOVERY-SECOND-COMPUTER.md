# Recovery on your second computer

Keep encrypted .cbk backups and the encrypted .cbrk recovery key on your second computer. Keep the recovery passphrase separately, such as in your password manager. The passphrase should be unique; knowing the passphrase and possessing these files permits recovery of customer records and service settings.

1. In an interactive terminal on the original computer, run `python -m ops.recovery_export export --recovery-file <new-private-file.cbrk>`. The program prompts without displaying the passphrase and refuses to overwrite an existing export. It reads the existing Windows-protected master key; it does not rotate keys or touch the live service.
2. Transfer the encrypted recovery file and a current encrypted .cbk backup using your chosen private transfer method. No transfer destination or shared/cloud folder is automatically selected.
3. On your second computer, use the reviewed project source and verified Python/cryptography runtime. Run `python -m ops.recovery_export drill --recovery-file <file.cbrk> --backup-file <file.cbk>`. Enter the phrase only in the hidden local terminal prompt.
4. A successful drill reports integrity, foreign-key and all-table matches. It does not overwrite a production database or print records/keys. A real second-computer success is required; tests with synthetic keys do not establish that your transferred files work.

The first export is currently waiting for owner input. Never send the recovery passphrase through this chat, support reports, email, logs or command arguments. Future encrypted backups use the same protected master key unless a separate reviewed rotation is performed.
