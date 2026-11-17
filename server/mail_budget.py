"""Shared attempt ceiling for the free launch mail plan, across every SMTP flow."""
import os
import time

class MailLimitReached(RuntimeError):
    pass

def reserve_mail(store):
    try:
        daily=int(os.getenv('CLIPBOT_MAIL_DAILY_LIMIT','90'))
        monthly=int(os.getenv('CLIPBOT_MAIL_MONTHLY_LIMIT','2700'))
        if not 0<=daily<=90 or not 0<=monthly<=2700:raise ValueError()
    except ValueError:
        raise RuntimeError('Invalid mail attempt limit; sending is paused.') from None
    now=time.time()
    with store.connection(atomic=True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS mail_attempts(created REAL NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS mail_attempts_created ON mail_attempts(created)')
        db.execute('DELETE FROM mail_attempts WHERE created<?',(now-31*86400,))
        counts=db.execute('SELECT COUNT(*),COALESCE(SUM(created>?),0) FROM mail_attempts',(now-86400,)).fetchone()
        if counts[0]>=monthly or counts[1]>=daily:raise MailLimitReached('Email attempt limit reached. Try again later.')
        # Commit before network I/O. Failed/unknown sends consume an attempt too.
        db.execute('INSERT INTO mail_attempts VALUES(?)',(now,))
