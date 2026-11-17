# Render build bootstrap review — October 15, 2026

Render build logs showed pip 25.0.1. The public advisory audit for that version
reported known vulnerabilities, including fixes first available in pip 26.2.
Some older archive-extraction findings are mitigated by Python 3.12; that does
not establish that every reported finding is exploitable in this deployment.

The proposed build upgrades only pip to 26.2.1 from an exact SHA-256-pinned wheel
before installing the existing application lock. Both installs use isolated
pip configuration and disable version checks. The bootstrap disables dependency
resolution and its lock requires hashes, binary distributions and the official
PyPI index. The existing pre-install policy command now checks both locks and
rejects bootstrap packages or versions outside the reviewed pip-only policy.

## Verification

- A disposable Windows Python 3.12.14 environment upgraded its fresh ensurepip
  pip 25.0.1 to 26.2.1 using the bootstrap lock. The downloaded wheel hash was
  `71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e`.
- Reinstalling with a deliberately all-zero hash exited 1 with a hash mismatch,
  before replacing the installed pip. It remained 26.2.1.
- The upgraded disposable environment installed all 39 hash-locked application
  packages successfully; `python -m pip check` reported no broken requirements.
- `python tools/dependency_policy.py` accepted one build tool and 39 application
  packages. Five focused dependency-policy tests passed. The three new negative
  entry-point cases first failed against the old checker, then passed after the
  bootstrap check was added: old pip, unreviewed package and unreviewed index.
- The existing separate pip-audit 2.10.1 tools queried the public advisory feed
  for pip 26.2.1 with dependency resolution disabled: one package checked, zero
  known vulnerabilities, zero skipped packages, exit 0. This is a dated advisory
  result, not a guarantee against undisclosed issues.
- Whitespace/diff validation passed. Application code and runtime dependencies
  were unchanged, so the full application suites were not repeated for this
  build-only change.

This check covers local Windows wheel installation. It does not establish a
successful Linux Render build. No commit, deployment or Render setting change
was performed for this review; the existing hosted build command must be updated
and a fresh hosted build verified before calling the deployed builder fixed.

## Private launch gates

Public signup, customer AI, live billing acceptance and the public companion
installer remain closed. The existing $400/month and $20/day Claude limits remain
in place. Native source/license and installer acceptance, live billing/webhook
acceptance, second-computer recovery and recurring backups, social approvals and
multi-account publishing, the fresh-customer journey and the final deployed
security audit remain gates described in the launch acceptance record. This
bootstrap change neither opens nor satisfies those gates.

## Hosted verification after review

Commit `ceb460f9bd314bf378da2e02f7e194a3ccd8c98b` was deployed to the existing private Render service on October 15. Its build completed in 1m01s after the saved build command was updated to the reviewed bootstrap. A private version check confirmed actual pip 26.2.1; health returned 200/ok/prelaunch, unchanged billing sources matched Git bytes, and every public launch switch remained closed. No new package names, customer data changes or paid service were introduced.
