# Support report email delivery

The owner-confirmed support inbox is `support@your-domain.example`. Submissions contain text only, with no attachments, automatic logs, or client-selected recipients. Report text is never interpreted as HTML or placed in email headers.

Configure an existing authenticated mail service in the hosting provider's secret environment settings. Do not commit credentials or paste them into chat. Required names:

- `CLIPBOT_REPORT_FROM`: sender address authorized by the mail service.
- `CLIPBOT_REPORT_SMTP_HOST`: your existing mail service's SMTP hostname.
- `CLIPBOT_REPORT_SMTP_PORT`: 465 for TLS or 587 for STARTTLS; insecure ports are rejected.
- `CLIPBOT_REPORT_SMTP_USERNAME`: authenticated sending account.
- `CLIPBOT_REPORT_SMTP_PASSWORD`: SMTP credential or app password.
- `CLIPBOT_REPORT_EMAIL`: optional operator-controlled override of the confirmed inbox; never read from a submitted report.

Without valid configuration, reports are saved for review and the interface says email is not configured. Existing saved reports are not automatically emailed after configuration. With configuration, submissions are queued and a background worker attempts one email per minute. A mail server accepting a message does not prove inbox delivery.

Limits are persisted in the database: five submissions per account per day, ten per IP per day, 100 globally per day, at most 100 queued messages, and at most 50 mail attempts per day. Identical reports from the same account reuse the original reference for 24 hours. Completed anti-abuse records expire after 30 days. The existing support report retention policy still applies to report contents.

Every message is claimed durably before network access. Timeouts and crashes retain an unknown delivery status and never cause automatic resending. Review unknown messages manually using the existing private reports operator workflow. Submitted reports cannot trigger bulk messages or send files. Tests use fake mail transports and never contact a real inbox.
