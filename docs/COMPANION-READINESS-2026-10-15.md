# Companion production-readiness follow-up — October 15, 2026

Public release remains blocked. These changes do not publish or install a new
Companion, enable customer analysis, change billing, or start monitoring.

## Customer pairing page

The packaged entry point still uses the fixed production origin
`https://clipbot.your-domain.example` and the loopback Companion at port 8767. Its
customer page now identifies Companion version 0.2.8, explains the one-time pairing
code, shows clear connection feedback and readable device health, and links to
the production website and initial setup guide. The old first-live-test language
and raw metric JSON are removed. An obsolete second capacity selector is removed;
scout settings remain in Streamers and are governed by server plan limits. The
legacy pairing API field remains compatible with older clients.

Codes are cleared on submission, never stored in browser storage, and submitted
only with the existing local exact Host, loopback, Origin, CSRF and body-size
checks. Status/error text uses textContent. Duplicate submits are blocked while
pending. Pairing does not start monitoring or publish anything.

The website connection guides now list verified Twitch developer email/2FA,
redirect and chat-read requirements, and Kick developer 2FA, channel-consent and
webhook requirements. Developer-app settings are labeled as app-owner duties;
ordinary customers authorize ClipBot rather than create apps or supply secrets.
Kick chat cues are not promised solely because OAuth succeeded.

Primary references:
- https://dev.twitch.tv/docs/authentication/register-app/
- https://docs.kick.com/getting-started/kick-apps-setup
- https://docs.kick.com/events/introduction

## Executable selection and plugins

Frozen capture, probe, rolling-buffer, render, review-preview and diagnostics
now select absolute bundled FFmpeg/ffprobe paths. Missing or linked tools fail
without CWD/PATH fallback; the bundled downloader follows the same selector.
Source development retains its explicit existing PATH-based prerequisites.
Frozen readiness checks require the bundled downloader, not merely an importable
Python package. This closes executable-selection gaps; it is not a claim that
same-user tampering with the installed application cannot occur.

The downloader ignores ambient configuration and disables external plugin
directories, remote components and JavaScript runtimes for Twitch/Kick stream
resolution. The pinned 2026.08.19 package accepts all options and enumerates its
extractors offline. No live provider capture or paid AI call was used here.

## Verification

- Focused security/media suite: 45 passed before the final capacity-UI cleanup.
- Full Python suite: 743 passed in 195.78 seconds.
- Final pairing/tool checks after capacity cleanup: 7 passed.
- Browser regression suite: 189 passed.
- Exact shipped setup script exercised for CSRF, cleared codes, duplicate
  prevention, text-only rendering, readable health and success/failure states.
- pip check: no broken requirements.
- Current pip-audit advisory query: 64 locked dependencies, zero known
  vulnerabilities and zero skipped records. This covers Python distributions,
  not every bundled native DLL or a malware certification.
- Release verifier still rejects sourceComplete=false. No incomplete installer
  was compiled or promoted. The temporary visual preview does not pair devices
  and is not part of the shipped application.

## Remaining native evidence

The exact vendor revision's successful Windows x64 CI runs are now located:
28393781929/job/84127236786 and 28139818759/job/83334584701. Public artifact lists
were empty and public log requests returned 403. This does not prove deletion,
but the missing historical runtime/toolchain packages and fetched helper files
were not recovered. Existing native-source and license gates stay closed.

Required next: complete Gyan and PyAV corresponding-source/license materials or
build reviewed replacements; obtain legitimate publisher signing; accept the
actual installer through a clean Windows install/update/uninstall and full local
pipeline. Windows Sandbox is unavailable on this PC. No paid signing service,
vendor contact or changes to the existing running Companion were performed.
