"""Revocable automatic decisions through the existing durable publishing broker."""
import json,os,time
from datetime import datetime,timezone
from .davey import candidate_hash
from .publication import PublicationDenied
from .worker_jobs import device_user,WorkerDenied
from .scouts import limits_in
from .legal import POLICY_VERSION


class DaveyAutomation:
    def __init__(self,store,pub):self.store=store;self.pub=pub

    def guard(self,db,uid,clip,platform,binding):
        """Called in reservation, grant and final mutation transactions."""
        if os.getenv('CLIPBOT_AUTONOMY_ENABLED')!='1' or self.store.billing_mode!='live':raise PublicationDenied('Automatic posting is paused.')
        settings,revision=self.store.davey._settings(db,uid)
        status=self.store.davey._status(db,uid,settings,revision)
        if not status['qualified'] or not settings['automatic'] or not settings['rightsAccepted'] or platform not in settings['platforms'] or revision!=binding.get('revision') or status['contextKey']!=binding.get('contextKey'):raise PublicationDenied('Davey permission or validation changed. Review this clip manually.')
        coverage,billing=self.pub.active_coverage(db,uid)
        day=datetime.now(timezone.utc).strftime('%Y-%m-%d')
        plan_cap=(20 if billing['plan'] in ('starter','creator') else None) if billing else coverage['posts']
        capacity=db.execute("SELECT COUNT(*) FROM clip_capacity WHERE user_id=? AND day=? AND status IN ('reserved','published')",(uid,day)).fetchone()[0]
        current=db.execute('SELECT 1 FROM clip_capacity WHERE user_id=? AND clip_id=? AND day=?',(uid,clip,day)).fetchone()
        if plan_cap is not None and capacity+(0 if current else 1)>plan_cap:raise PublicationDenied('Your current daily posting allowance is reached.')
        if not db.execute('SELECT 1 FROM email_verification WHERE user_id=?',(uid,)).fetchone() or not db.execute('SELECT 1 FROM legal_acceptances WHERE user_id=? AND version=?',(uid,POLICY_VERSION)).fetchone():raise PublicationDenied('Current account verification and policies are required.')
        prefs=db.execute('SELECT data FROM preferences WHERE user_id=?',(uid,)).fetchone()
        scout=db.execute('SELECT data FROM scout_settings WHERE user_id=?',(uid,)).fetchone()
        if not prefs or json.loads(prefs[0]).get('usagePreset','paused')=='paused' or not scout or not json.loads(scout[0]).get('running') or limits_in(db,uid)['scouts']<=0:raise PublicationDenied('ClipBot or Davey is stopped.')
        run=db.execute('SELECT started FROM debug_sessions WHERE id=? AND user_id=? AND stopped IS NULL',(binding.get('runId'),uid)).fetchone()
        if not run:raise PublicationDenied('The monitoring session ended.')
        job=db.execute('SELECT * FROM pipeline_jobs WHERE id=? AND user_id=?',(clip,uid)).fetchone()
        if not job or job['device']!=binding.get('device') or job['lease_expires']<=time.time() or not db.execute('SELECT 1 FROM worker_devices WHERE user_id=? AND token=? AND expires>?',(uid,binding.get('device'),time.time())).fetchone():raise PublicationDenied('The paired capture lease is unavailable.')
        if job['created']<run['started']:raise PublicationDenied('This clip belongs to an earlier monitoring session.')
        if json.loads(job['source']) not in settings['sources']:raise PublicationDenied('This stream source was not approved for automatic posting.')
        review=db.execute('SELECT data FROM reviews WHERE user_id=? AND candidate_id=?',(uid,clip)).fetchone()
        if review and json.loads(review[0]).get('actor','human')!='davey':raise PublicationDenied('A human decision takes priority.')
        candidate=db.execute('SELECT data FROM candidates WHERE id=? AND user_id=?',(clip,uid)).fetchone()
        prediction=db.execute('SELECT * FROM davey_predictions WHERE user_id=? AND job_id=?',(uid,clip)).fetchone()
        if not candidate or not prediction:raise PublicationDenied('A fresh measured prediction is required.')
        candidate=json.loads(candidate[0])
        if candidate.get('safetyFlags')!=[] or prediction['decision']!='approve' or not prediction['safety_ok'] or prediction['invalidated'] or prediction['human_decision'] is not None or prediction['context_key']!=status['contextKey'] or candidate_hash(candidate)!=prediction['candidate_hash']:raise PublicationDenied('This clip needs manual review.')
        artifact=db.execute('SELECT data FROM clip_artifacts WHERE user_id=? AND clip_id=?',(uid,clip)).fetchone()
        if not artifact:raise PublicationDenied('A verified final render is required.')
        artifact=json.loads(artifact[0]);self.pub.validate_artifact(artifact)
        if (artifact.get('width'),artifact.get('height'),artifact.get('framing'))!=(1080,1920,'blurred_fit'):raise PublicationDenied('A captioned mobile render is required.')
        consent=db.execute('SELECT * FROM davey_destination_consent WHERE user_id=? AND platform=?',(uid,platform)).fetchone()
        _,destination,version=self.pub.credentials(uid,platform)
        if not consent or consent['revision']!=revision or destination!=consent['destination'] or version!=consent['authorization_version']:raise PublicationDenied('The approved publishing account changed.')
        day=datetime.now(timezone.utc).strftime('%Y-%m-%d')
        used=db.execute("SELECT DISTINCT clip_id FROM publications WHERE user_id=? AND day=? AND automation IS NOT NULL",(uid,day)).fetchall()
        cap=settings['dailyPostLimit']
        if clip not in {row[0] for row in used} and len(used)>=cap:raise PublicationDenied('Your daily automatic clip limit is reached.')
        return candidate

    def binding(self,db,uid,token_hash):
        settings,revision=self.store.davey._settings(db,uid)
        run=db.execute('SELECT id FROM debug_sessions WHERE user_id=? AND stopped IS NULL ORDER BY started DESC LIMIT 1',(uid,)).fetchone()
        return {'revision':revision,'contextKey':self.store.davey._context_key(db,uid,settings),'runId':run[0] if run else None,'device':token_hash}

    def reserve_in(self,db,uid,clip,platform,binding):
        candidate=self.guard(db,uid,clip,platform,binding)
        value={'actor':'davey','candidate':candidate,'user_feedback':{'decision':'approve','reasons':[],'justification':''},'syncStatus':'server','reviewedAt':time.time()}
        db.execute('INSERT OR IGNORE INTO reviews VALUES(?,?,?)',(uid,clip,json.dumps(value)))
        db.execute('UPDATE davey_predictions SET automated=1 WHERE user_id=? AND job_id=?',(uid,clip))

    def dispatch(self,uid,token):
        from .store import token_hash
        prepared=0
        with self.store.connection() as db:
            try:
                if device_user(db,token)!=uid:raise WorkerDenied('Reconnect your worker.')
            except WorkerDenied as error:raise PublicationDenied(str(error)) from None
            binding=self.binding(db,uid,token_hash(token))
            rows=db.execute("SELECT j.id FROM pipeline_jobs j JOIN clip_artifacts a ON a.clip_id=j.id AND a.user_id=j.user_id WHERE j.user_id=? AND j.device=? AND j.stage IN ('review','ready','publishing') ORDER BY j.created LIMIT 5",(uid,token_hash(token))).fetchall()
        # Bounded work, no model call, and no retry of an existing attempt.
        for row in rows:
            for platform in self.store.davey.settings(uid)['platforms']:
                if prepared>=2:return {'prepared':prepared}
                try:
                    with self.store.connection() as db:candidate=self.guard(db,uid,row['id'],platform,binding)
                    self.pub.prepare(uid,row['id'],platform,{'title':candidate['title'],'caption':candidate['caption'],'rightsAccepted':True},automation=binding)
                    prepared+=1
                except (PublicationDenied,WorkerDenied):continue
        return {'prepared':prepared}
