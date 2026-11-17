# ClipBot Companion 0.2.8 — second-PC acceptance checklist

Status: a private unsigned 0.2.8 installer is built and locally tested; see [build results](COMPANION-SELF-BUILD-RESULTS-2026-10-15.md). Clean-PC acceptance and public release remain pending. This file is a checklist, not an installer. Do not use the compiler recipe-check artifact or an older installer as a substitute.

Use your second Windows PC with a standard Windows user account. Keep backups, passwords, API keys, customer databases and pairing/device files from the first PC off this test PC. Pair the second PC independently when a matching hosted release is available.

## Before installation

- Receive the exact installer, its SHA256/size manifest, publisher information, license notices and corresponding-source release evidence from this chat or the approved official download.
- Verify its file hash against that manifest. Record the actual digital-signature status. This private candidate is unsigned; that does not pass the production publisher-signing gate. Any Windows approval must be handled by the owner, with protections kept enabled. Do not mark an unknown-publisher warning as a valid signature.
- Run the PC's normal antivirus check on the exact installer. Record the tool, date and result.
- Record Windows version, processor architecture and whether ClipBot was previously installed. Do not record the machine name, account password or personal files.

## Fresh installation

- Install as the standard user. It should not need an administrator password and should default to the user's local Programs folder.
- Leave “Start ClipBot Companion … when I sign in” unchecked. Verify the tray app launches once, the local setup page opens at http://127.0.0.1:8767/, version is 0.2.8, and bundled tools/model are available.
- Confirm the tray icon remains usable after closing the browser page. Starting the app again should not launch duplicate workers.
- Exit using the tray menu; verify the local setup service stops. Restart the app normally.
- Enable startup in the companion, sign out/in to Windows and verify one instance starts. Disable startup and confirm it no longer starts at sign-in.

## Upgrade

- Use only a separately verified previous installer if an upgrade test is required. Keep an existing startup entry enabled, then upgrade while explicitly unchecking startup. Confirm the previous entry is removed.
- Verify the new version, model, tools and shortcuts. Confirm a single tray/worker instance remains and valid pairing is preserved where intended.
- Do not override a server/worker version mismatch. Production pairing and full publishing acceptance need the matching hosted release and are separate from this installation-only checklist.

## Uninstall and reinstall

- Stop active processing and exit the companion. Uninstall using Windows Installed Apps.
- Confirm the program files, program shortcut, ClipBot startup value and clipbot-companion URL registration are removed. The local service should remain stopped after another Windows sign-in.
- Record whether the separate per-user data folder remains. Do not assume uninstall deletes local clip history or revokes the device on the service; disconnect/revoke the device through the account flow before disposing of a PC.
- Reinstall the verified release; verify setup works without an old process or stale startup entry.

## Results

For each step record PASS, FAIL or NOT RUN, with a short observation. Do not mark the whole release accepted while steps remain NOT RUN. Send only these results, installer hash/version and sanitized error details; never send passwords, pairing codes, access tokens or customer recordings.
