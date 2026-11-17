# ClipBot launch completion implementation plan

> For agentic workers: use superpowers:executing-plans to implement task by task.

**Goal:** Complete release preparation and record evidence for the owner's fresh-email acceptance run and final security audit.
**Architecture:** Keep media/local processing on the companion; enforce accounts, billing, budget and coordination on the server. Fail release packaging when an input cannot be verified. Existing production gates remain off until provider and installed-app acceptance passes.
**Tech Stack:** Python/FastAPI, vanilla JavaScript, Windows/PyInstaller/Inno Setup, Stripe, Resend and Cloudflare.
**Spec:** User's launch instructions in this chat and docs/COMPANION-PROVENANCE-AUDIT.md.

## Global constraints
- Free services only; seek approval before paid services.
- Preserve $400/month and $20/day Claude ceilings.
- No real payment, legal consent, or new credential entered on the owner's behalf.
- TikTok restriction applies to owner's current developer account, not a generic launch blocker.
- Never report a security guarantee; distinguish simulated checks from installed/provider acceptance.

## Review focus
- Altered model/binary input must fail before loading or executing.
- Symlink/path traversal must not let build inputs escape the checkout.
- Incomplete license/source or dependency inventories must prevent public packaging.
- Prompt/file/header injection must never produce tool execution or mail attachments.
- Unknown payment/delivery outcomes must reconcile without repeating charges/messages.

## Tasks
- [x] Add tested release-input manifest verification and eliminate mutable PATH binary selection.
- [x] Verify pinned model hashes before loading, and test missing/modified inputs.
- [ ] Finish exact worker/build lock and matching source/license inventory; compile only when evidence is complete.
- [ ] Test updated installed companion on clean Windows: pairing, capture, transcript, editing, approval, publish, revocation, update/uninstall.
- [ ] Verify real billing lifecycle with owner financial actions handed off; preserve all plan limits.
- [ ] Finalize independent backup-key custody, restore proof and monitoring operations.
- [ ] Owner creates fresh email and completes entire customer journey.
- [ ] Run final deployed website/Davey/email/file-security audit, dependency checks and complete regression suite; record exact revision/artifact/gates.
