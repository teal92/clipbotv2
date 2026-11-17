# Beta patch release procedure

Use semantic versions `0.MINOR.PATCH` during beta. Reliability/security fixes increment PATCH; new capabilities increment MINOR. Start the traceable patch series at 0.2.9; do not invent historical binary provenance.

1. Reproduce failures with regression tests. Review security, account isolation, spend caps and request retry behavior. Run backend/security and frontend suites.
2. Commit all reviewed source, including new files. The build refuses a dirty tree or untracked source. Tag the reviewed release commit as `companion-beta-vVERSION` after verification.
3. Archive the prior installer and manifest with their verified hashes outside the build output. Preserve a recoverable rollback copy.
4. Use the existing approved, pinned Python build environment and `packaging/build-companion.ps1 -Python <approved-python> -PreviousVersion 0.2.8` for 0.2.9. The script validates the one-step patch increment before building, verifies provenance and dependency policy, audits the frozen bundle, and records `sourceCommit`, `releaseKind`, `previousVersion`, size and hash.
5. Run frozen media diagnostics with separate AppData and synthetic media. Verify no real pairing changes, paid requests or social posts. Then test the actual installer/update and pairing. A prior version's acceptance does not qualify a new artifact.
6. Keep new artifacts internal until accepted. Do not claim code signing or clean-machine acceptance that has not occurred. Public unsigned beta downloads retain a clear warning and explicit version/hash acknowledgement.
7. Deploy verified server changes independently where safe. The companion version requirement follows the installer actually available, so a server-only deployment does not demand an unavailable update.
8. Promote the accepted artifact and matching manifest together, verify hosted hashes and availability, and retain the prior rollback artifact. Never overwrite an in-use download inode or disable integrity checks to complete an update.

Customer update: stop ClipBot, close the companion, run the beta patch installer and reconnect/check status. The stable installer AppId preserves the install location; pairing and local data live outside the application directory. Verify these remain intact before promoting a patch broadly.
