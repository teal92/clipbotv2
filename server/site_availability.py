"""Persistent visitor-site maintenance control; never changes release permissions."""
import json,os,time
from fastapi import HTTPException
from starlette.responses import JSONResponse,HTMLResponse


class SiteAvailability:
    def __init__(self,store):
        self.store=store
        with store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS site_availability(id INTEGER PRIMARY KEY CHECK(id=1),online INTEGER NOT NULL CHECK(online IN (0,1)),revision INTEGER NOT NULL,changed REAL)')
            db.execute('INSERT OR IGNORE INTO site_availability VALUES(1,1,0,NULL)')

    def snapshot(self,db=None):
        if db is None:
            with self.store.connection() as connection:return self.snapshot(connection)
        row=db.execute('SELECT online,revision,changed FROM site_availability WHERE id=1').fetchone()
        if not row:raise RuntimeError('Website availability is unavailable')
        public=os.getenv('CLIPBOT_PUBLIC_SIGNUP')=='1' and os.getenv('CLIPBOT_SIGNUP_EMAIL_HASHES') is None
        return {'online':bool(row['online']),'revision':row['revision'],'changedAt':row['changed'],
                'audience':'public registration' if public else 'private preview','source':'ClipBot persistent site control',
                'releasePermissionsUnchanged':True}

    def change(self,online,revision):
        with self.store.connection(atomic=True) as db:
            current=self.snapshot(db)
            if current['revision']!=revision:raise HTTPException(409,'Website status changed. Refresh before trying again.')
            db.execute('UPDATE site_availability SET online=?,revision=revision+1,changed=? WHERE id=1',(int(online),time.time()))
            return self.snapshot(db)


class SiteAvailabilityMiddleware:
    def __init__(self,app,control):self.app=app;self.control=control
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        path=scope.get('path','')
        # Preserve private recovery, health probes and signed provider callbacks.
        # The website switch does not kill an already-running companion session.
        existing_worker=path.startswith('/api/worker/') and path not in ('/api/worker/pairing','/api/worker/connect')
        exempt=path in ('/healthz','/api/billing/webhook','/api/events/kick/chat') or path.startswith('/api/operator/') or existing_worker
        if not exempt:
            from starlette.concurrency import run_in_threadpool
            try:online=(await run_in_threadpool(self.control.snapshot))['online']
            except Exception:online=False
            if not online:
                headers={'Retry-After':'300','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
                text='ClipBot is temporarily offline for maintenance. Please check back shortly.'
                response=JSONResponse({'detail':text},status_code=503,headers=headers) if path.startswith('/api/') else HTMLResponse('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ClipBot maintenance</title><h1>ClipBot is temporarily offline</h1><p>We are performing maintenance. Please check back shortly.</p></html>',status_code=503,headers=headers)
                return await response(scope,receive,send)
        return await self.app(scope,receive,send)
