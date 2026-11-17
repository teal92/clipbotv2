"""Account-scoped resumable publication with atomic clip capacity and receipts."""
import hashlib,json,math,re,secrets,time
from datetime import datetime,timezone
from urllib.parse import urlsplit
from .worker_jobs import device_user,WorkerDenied
from .oauth import OAuthUnavailable

from clipbot_common.upload_urls import PublicationDenied, validate_upload_url

def provider_id(value):
    if not isinstance(value,(int,str)) or not re.fullmatch(r'[0-9]{1,100}',str(value)):raise PublicationDenied('The provider returned an invalid media identifier.')
    return str(value)

class PublicationService:
    def __init__(self,store,oauth):
        self.store=store;self.oauth=oauth;self.cipher=oauth.vault.cipher
        from .publishing_diagnostics import PublishingDiagnostics
        self.diagnostics=PublishingDiagnostics(store)
        with store.connection() as db:db.executescript("""
        CREATE TABLE IF NOT EXISTS clip_artifacts(user_id TEXT NOT NULL,clip_id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(user_id,clip_id));
        CREATE TABLE IF NOT EXISTS clip_capacity(user_id TEXT NOT NULL,clip_id TEXT NOT NULL,day TEXT NOT NULL,status TEXT NOT NULL,PRIMARY KEY(user_id,clip_id,day));
        CREATE TABLE IF NOT EXISTS publications(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,clip_id TEXT NOT NULL,platform TEXT NOT NULL,day TEXT NOT NULL,status TEXT NOT NULL,remote_id TEXT,payload TEXT,receipt TEXT,lease_expires REAL NOT NULL DEFAULT 0,finish_started INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,updated REAL NOT NULL,UNIQUE(user_id,clip_id,platform));
        CREATE INDEX IF NOT EXISTS publications_owner ON publications(user_id,created);
        """)
        with store.connection() as db:
            if 'finish_started' not in {r[1] for r in db.execute('PRAGMA table_info(publications)')}:db.execute('ALTER TABLE publications ADD COLUMN finish_started INTEGER NOT NULL DEFAULT 0')
            if 'lease_owner' not in {r[1] for r in db.execute('PRAGMA table_info(publications)')}:db.execute("ALTER TABLE publications ADD COLUMN lease_owner TEXT NOT NULL DEFAULT ''")
            if 'automation' not in {r[1] for r in db.execute('PRAGMA table_info(publications)')}:db.execute('ALTER TABLE publications ADD COLUMN automation TEXT')
        from .davey_automation import DaveyAutomation
        self.automation=DaveyAutomation(store,self);store.davey_publications=self
    @staticmethod
    def active_coverage(db,uid):
        from .billing_modes import entitlement_allowed
        if not entitlement_allowed(db,uid):raise PublicationDenied('Active plan coverage is required.')
        from .owner_showcase import operational_coverage,operational_billing
        coverage=operational_coverage(db,uid)
        billing=operational_billing(db,uid)
        if not coverage or (billing and (billing['status']!='active' or billing['expires']<=time.time())):
            raise PublicationDenied('Active plan coverage is required.')
        return coverage,billing
    @staticmethod
    def public(row):return {'id':row['id'],'clipId':row['clip_id'],'platform':row['platform'],'status':row['status'],'receipt':json.loads(row['receipt']) if row['receipt'] else None,'updated':row['updated']}
    def snapshot(self,uid):
        with self.store.connection() as db:return [self.public(row) for row in db.execute('SELECT * FROM publications WHERE user_id=? ORDER BY created DESC LIMIT 100',(uid,))]
    def reserve(self,uid,clip_id,platform,*,artifact_hash=None,automation=None):
        if platform not in ('facebook','instagram','tiktok') or not isinstance(clip_id,str) or not 1<=len(clip_id)<=100:raise PublicationDenied('Invalid publication request.')
        now=time.time();day=datetime.now(timezone.utc).strftime('%Y-%m-%d');attempt=secrets.token_hex(16)
        with self.store.connection(atomic=True) as db:
            coverage,billing=self.active_coverage(db,uid)
            if automation is not None:self.automation.reserve_in(db,uid,clip_id,platform,automation)
            if artifact_hash is not None:
                clip=db.execute("SELECT a.data FROM clip_artifacts a JOIN pipeline_jobs j ON j.id=a.clip_id AND j.user_id=a.user_id WHERE a.user_id=? AND a.clip_id=? AND (j.stage IN ('ready','publishing','published') OR (? AND j.stage='review'))",(uid,clip_id,automation is not None)).fetchone()
                if not clip or json.loads(clip['data'])['sha256']!=artifact_hash:raise PublicationDenied('Rendered clip was cancelled or changed.')
            cap=(20 if billing['plan'] in ('starter','creator') else None) if billing else coverage['posts']
            old=db.execute('SELECT 1 FROM publications WHERE user_id=? AND clip_id=? AND platform=?',(uid,clip_id,platform)).fetchone()
            if old:raise PublicationDenied('This destination already has a publication attempt. Check its status before retrying.')
            capacity=db.execute('SELECT 1 FROM clip_capacity WHERE user_id=? AND clip_id=? AND day=?',(uid,clip_id,day)).fetchone()
            if not capacity:
                count=db.execute("SELECT COUNT(*) FROM clip_capacity WHERE user_id=? AND day=? AND status IN ('reserved','published')",(uid,day)).fetchone()[0]
                if cap is not None and count>=cap:raise PublicationDenied('Your daily unique clip allowance is reached.')
                db.execute("INSERT INTO clip_capacity VALUES(?,?,?,'reserved')",(uid,clip_id,day))
            db.execute('INSERT INTO publications(id,user_id,clip_id,platform,day,status,created,updated) VALUES(?,?,?,?,?,?,?,?)',(attempt,uid,clip_id,platform,day,'initializing',now,now))
            if automation is not None:db.execute('UPDATE publications SET automation=? WHERE id=?',(json.dumps(automation),attempt))
            if artifact_hash is not None:db.execute("UPDATE pipeline_jobs SET stage='publishing',updated=? WHERE id=? AND user_id=?",(now,clip_id,uid))
        self.diagnostics.emit(uid,clip_id,attempt,platform,'initializing')
        return attempt
    @staticmethod
    def validate_artifact(data):
        if not isinstance(data,dict) or set(data)-{'sha256','sizeBytes','duration','width','height','framing','previewToken'} or not re.fullmatch(r'[a-f0-9]{64}',str(data.get('sha256',''))) or type(data.get('sizeBytes')) is not int or not 1<=data['sizeBytes']<=128*1024**2 or type(data.get('duration')) not in (int,float) or not math.isfinite(data['duration']) or not 14.5<=data['duration']<=60.5:raise PublicationDenied('Invalid rendered clip metadata.')
    def artifact(self,uid,clip_id,data):
        self.validate_artifact(data)
        with self.store.connection(atomic=True) as db:
            if not db.execute('SELECT 1 FROM pipeline_jobs WHERE id=? AND user_id=?',(clip_id,uid)).fetchone():raise PublicationDenied('Clip not found in your account.')
            if db.execute('SELECT 1 FROM publications WHERE clip_id=? AND user_id=?',(clip_id,uid)).fetchone():raise PublicationDenied('A publication already locks this rendered artifact.')
            db.execute('INSERT OR REPLACE INTO clip_artifacts VALUES(?,?,?)',(uid,clip_id,json.dumps(data)))
    def credentials(self,uid,platform):
        record=self.oauth.vault.load(uid,platform)
        if not record or record['tokens']['expires_at']<=time.time()+60:raise PublicationDenied('Reconnect this publishing account.')
        if platform=='tiktok':
            if 'video.publish' not in record['tokens'].get('scopes',[]):raise PublicationDenied('TikTok publishing permission is unavailable.')
            return record['tokens']['access_token'],None,record['_version']
        profile=record['profile'];dest=next((d for d in record['tokens'].get('destinations',[]) if d['id']==profile.get('destinationId')),None)
        if not profile.get('destinationSelected') or not dest:raise PublicationDenied('Select an authorized publishing destination.')
        return dest['access_token'],provider_id(dest['id']),record['_version']
    def creator_info(self,uid):
        token,_,_=self.credentials(uid,'tiktok')
        data=self.oauth.request('POST','https://open.tiktokapis.com/v2/post/publish/creator_info/query/',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},json={})
        if data.get('error',{}).get('code')!='ok' or not isinstance(data.get('data'),dict):raise PublicationDenied('TikTok creator settings are unavailable.')
        info=data['data'];levels=info.get('privacy_level_options')
        if not isinstance(levels,list) or any(v not in ('PUBLIC_TO_EVERYONE','MUTUAL_FOLLOW_FRIENDS','FOLLOWER_OF_CREATOR','SELF_ONLY') for v in levels):raise PublicationDenied('TikTok returned invalid privacy settings.')
        return {k:info.get(k) for k in ('creator_nickname','creator_username','privacy_level_options','comment_disabled','duet_disabled','stitch_disabled','max_video_post_duration_sec')}
    def prepare(self,uid,clip_id,platform,options,*,automation=None):
        from .customer_access import require_customer_ready
        require_customer_ready(self.store,uid)
        if not self.cipher:raise PublicationDenied('Publishing encryption is not configured.')
        if not isinstance(options,dict) or set(options)-{'title','caption','rightsAccepted','privacy','disableComment','disableDuet','disableStitch'} or options.get('rightsAccepted') is not True or not isinstance(options.get('title'),str) or not 1<=len(options['title'])<=100 or not isinstance(options.get('caption'),str) or not 1<=len(options['caption'])<=2200:raise PublicationDenied('Review the caption and confirm permission to publish.')
        with self.store.connection() as db:
            job=db.execute("SELECT 1 FROM pipeline_jobs WHERE id=? AND user_id=? AND (stage IN ('ready','publishing','published') OR (? AND stage='review'))",(clip_id,uid,automation is not None)).fetchone();artifact=db.execute('SELECT data FROM clip_artifacts WHERE clip_id=? AND user_id=?',(clip_id,uid)).fetchone()
        if not job or not artifact:raise PublicationDenied('An owned, verified rendered clip is required.')
        artifact=json.loads(artifact['data']);token,destination,version=self.credentials(uid,platform)
        creator=self.creator_info(uid) if platform=='tiktok' else None
        if creator:
            if options.get('privacy') not in creator['privacy_level_options'] or artifact['duration']>creator.get('max_video_post_duration_sec',0) or artifact['sizeBytes']>64*1024**2:raise PublicationDenied('Choose supported TikTok privacy and video settings.')
            for field in ('disableComment','disableDuet','disableStitch'):
                if type(options.get(field)) is not bool:raise PublicationDenied('Review TikTok interaction settings.')
        attempt=self.reserve(uid,clip_id,platform,artifact_hash=artifact['sha256'],automation=automation);graph=f'https://graph.facebook.com/{self.oauth.version}'
        try:
            if automation is not None:
                with self.store.connection() as db:self.automation.guard(db,uid,clip_id,platform,automation)
            if platform=='facebook':
                result=self.oauth.request('POST',graph+'/'+destination+'/video_reels',headers={'Authorization':'Bearer '+token},data={'upload_phase':'start'})
                remote=provider_id(result.get('video_id'));url=result.get('upload_url')
            elif platform=='instagram':
                result=self.oauth.request('POST',graph+'/'+destination+'/media',headers={'Authorization':'Bearer '+token},data={'media_type':'REELS','upload_type':'resumable','caption':options['caption'],'share_to_feed':'true'})
                remote=provider_id(result.get('id'));url=result.get('uri') or result.get('upload_uri') or result.get('upload_url')
            else:
                size=artifact['sizeBytes']
                result=self.oauth.request('POST','https://open.tiktokapis.com/v2/post/publish/video/init/',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},json={'post_info':{'title':options['caption'],'privacy_level':options['privacy'],'disable_comment':options['disableComment'] or creator.get('comment_disabled',True),'disable_duet':options['disableDuet'] or creator.get('duet_disabled',True),'disable_stitch':options['disableStitch'] or creator.get('stitch_disabled',True)},'source_info':{'source':'FILE_UPLOAD','video_size':size,'chunk_size':size,'total_chunk_count':1}})
                if result.get('error',{}).get('code')!='ok':raise PublicationDenied('TikTok did not initialize the upload.')
                result=result.get('data',{});remote=result.get('publish_id');url=result.get('upload_url')
                if not isinstance(remote,str) or not 1<=len(remote)<=200:raise PublicationDenied('TikTok did not return a valid publish identifier.')
            validate_upload_url(url,platform,remote)
            payload={'url':url,'method':'PUT' if platform=='tiktok' else 'POST','headers':{'Content-Type':'video/mp4','Content-Range':f"bytes 0-{artifact['sizeBytes']-1}/{artifact['sizeBytes']}"} if platform=='tiktok' else {'Authorization':'OAuth '+token,'offset':'0','file_size':str(artifact['sizeBytes']),'Content-Type':'application/octet-stream'},'artifact':artifact,'destination':destination,'options':options,'authorizationVersion':version,'expiresAt':time.time()+900}
            encrypted=self.cipher.encrypt(json.dumps(payload).encode()).decode()
            with self.store.connection() as db:db.execute("UPDATE publications SET status='prepared',remote_id=?,payload=?,updated=? WHERE id=?",(remote,encrypted,time.time(),attempt))
        except Exception as error:
            with self.store.connection() as db:db.execute("UPDATE publications SET status='unknown',updated=? WHERE id=?",(time.time(),attempt))
            self.diagnostics.emit(uid,clip_id,attempt,platform,'unknown',code='initialization_unconfirmed',http_status=getattr(error,'http_status',None))
            raise PublicationDenied('Publication initialization did not finish. Check status; no automatic retry was started.') from None
        self.diagnostics.emit(uid,clip_id,attempt,platform,'prepared')
        return next(p for p in self.snapshot(uid) if p['id']==attempt)
    def grant(self,device_token,attempt_id):
        with self.store.connection(atomic=True) as db:
            try:uid=device_user(db,device_token)
            except WorkerDenied:raise PublicationDenied('Reconnect your worker.') from None
            row=db.execute("SELECT * FROM publications WHERE id=? AND user_id=? AND status='prepared'",(attempt_id,uid)).fetchone()
            if not row:raise PublicationDenied('This upload is unavailable or was already claimed.')
            from .customer_access import require_customer_ready
            require_customer_ready(self.store,uid,db=db)
            coverage,billing=self.active_coverage(db,uid)
            payload=json.loads(self.cipher.decrypt(row['payload'].encode()))
            if row['automation']:self.automation.guard(db,uid,row['clip_id'],row['platform'],json.loads(row['automation']))
            _,_,version=self.credentials(uid,row['platform'])
            if payload['expiresAt']<=time.time() or version!=payload['authorizationVersion']:raise PublicationDenied('Upload authorization expired or changed.')
            day=datetime.now(timezone.utc).strftime('%Y-%m-%d')
            cap=(20 if billing['plan'] in ('starter','creator') else None) if billing else coverage['posts']
            # Preparation may cross UTC midnight. A new upload grant must spend
            # today's capacity, not just the day when its provider was initialized.
            capacity=db.execute('SELECT 1 FROM clip_capacity WHERE user_id=? AND clip_id=? AND day=?',(uid,row['clip_id'],day)).fetchone()
            count=db.execute("SELECT COUNT(*) FROM clip_capacity WHERE user_id=? AND day=? AND status IN ('reserved','published')",(uid,day)).fetchone()[0]
            # A reservation from a larger plan does not authorize a new grant
            # after a same-day downgrade below already reserved daily usage.
            if cap is not None and count+(0 if capacity else 1)>cap:raise PublicationDenied('Your daily unique clip allowance is reached.')
            if not capacity:
                db.execute("INSERT INTO clip_capacity VALUES(?,?,?,'reserved')",(uid,row['clip_id'],day))
            db.execute("UPDATE publications SET status='uploading',day=?,updated=? WHERE id=?",(day,time.time(),attempt_id))
            grant_data={'attemptId':attempt_id,'clipId':row['clip_id'],'platform':row['platform'],'remoteId':row['remote_id'],'url':payload['url'],'method':payload['method'],'headers':payload['headers'],'artifact':payload['artifact'],'expiresAt':payload['expiresAt']}
        self.diagnostics.emit(uid,row['clip_id'],attempt_id,row['platform'],'uploading')
        return grant_data
    def uploaded(self,device_token,attempt_id):
        with self.store.connection(atomic=True) as db:
            uid=device_user(db,device_token)
            changed=db.execute("UPDATE publications SET status='uploaded',updated=? WHERE id=? AND user_id=? AND status='uploading'",(time.time(),attempt_id,uid)).rowcount
            if not changed:raise PublicationDenied('Upload receipt is unavailable or was already recorded.')
        with self.store.connection() as db:row=db.execute('SELECT clip_id,platform FROM publications WHERE id=? AND user_id=?',(attempt_id,uid)).fetchone()
        self.diagnostics.emit(uid,row['clip_id'],attempt_id,row['platform'],'uploaded')
        return self.reconcile(uid,attempt_id)
    def confirm(self,uid,row,receipt,lease_owner=None):
        with self.store.connection(atomic=True) as db:
            if lease_owner and not db.execute('SELECT 1 FROM publications WHERE id=? AND lease_owner=? AND lease_expires>?',(row['id'],lease_owner,time.time())).fetchone():return
            db.execute("UPDATE publications SET status='published',receipt=?,payload=NULL,updated=? WHERE id=? AND user_id=?",(json.dumps(receipt),time.time(),row['id'],uid))
            db.execute("UPDATE clip_capacity SET status='published' WHERE user_id=? AND clip_id=? AND day=?",(uid,row['clip_id'],row['day']))
            db.execute("UPDATE pipeline_jobs SET stage='published',updated=? WHERE id=? AND user_id=?",(time.time(),row['clip_id'],uid))
        self.diagnostics.emit(uid,row['clip_id'],row['id'],row['platform'],'published')
    def reconcile(self,uid,attempt_id):
        now=time.time();lease_owner=secrets.token_hex(16)
        with self.store.connection(atomic=True) as db:
            row=db.execute('SELECT * FROM publications WHERE id=? AND user_id=?',(attempt_id,uid)).fetchone()
            if not row:raise PublicationDenied('Publication not found.')
            if row['status'] in ('published','failed','prepared','initializing') or not row['remote_id'] or row['lease_expires']>now:return self.public(row)
            db.execute('UPDATE publications SET lease_expires=?,lease_owner=? WHERE id=?',(now+45,lease_owner,attempt_id))
        try:
            token,destination,_=self.credentials(uid,row['platform']);remote=row['remote_id'];graph=f'https://graph.facebook.com/{self.oauth.version}';headers={'Authorization':'Bearer '+token}
            if row['platform']=='tiktok':
                response=self.oauth.request('POST','https://open.tiktokapis.com/v2/post/publish/status/fetch/',headers={**headers,'Content-Type':'application/json'},json={'publish_id':remote})
                if response.get('error',{}).get('code')!='ok':raise PublicationDenied('TikTok status is unavailable.')
                status=response.get('data',{}).get('status')
                if status=='PUBLISH_COMPLETE':self.confirm(uid,row,{'providerId':remote,'kind':'publish_id','verifiedAt':time.time()},lease_owner)
                elif status=='FAILED':self.failed(uid,row,lease_owner)
            elif row['platform']=='instagram':
                status=self.oauth.request('GET',graph+'/'+remote,headers=headers,params={'fields':'status_code'}).get('status_code')
                if status=='PUBLISHED':self.confirm(uid,row,{'providerId':remote,'kind':'published_container','verifiedAt':time.time()},lease_owner)
                elif status in ('ERROR','EXPIRED'):self.failed(uid,row,lease_owner)
                elif status=='FINISHED' and not row['finish_started'] and row['status'] in ('uploaded','uploading','unknown'):
                    if not self.finishing(uid,row,lease_owner):return next(p for p in self.snapshot(uid) if p['id']==attempt_id)
                    result=self.oauth.request('POST',graph+'/'+destination+'/media_publish',headers=headers,data={'creation_id':remote})
                    self.confirm(uid,row,{'providerId':provider_id(result.get('id')),'kind':'media_id','verifiedAt':time.time()},lease_owner)
            else:
                data=self.oauth.request('GET',graph+'/'+remote,headers=headers,params={'fields':'status'}).get('status',{})
                publishing=data.get('publishing_phase',{})
                if str(publishing.get('status','')).lower()=='complete' and row['finish_started']:
                    self.confirm(uid,row,{'providerId':remote,'kind':'reel_id','verifiedAt':time.time()},lease_owner)
                elif str(data.get('processing_phase',{}).get('status','')).lower()=='error':self.failed(uid,row,lease_owner)
                elif not row['finish_started'] and (row['status']=='uploaded' or (row['status'] in ('uploading','unknown') and str(data.get('uploading_phase',{}).get('status','')).lower()=='complete')):
                    if not self.finishing(uid,row,lease_owner):return next(p for p in self.snapshot(uid) if p['id']==attempt_id)
                    result=self.oauth.request('POST',graph+'/'+destination+'/video_reels',headers=headers,data={'upload_phase':'finish','video_id':remote,'video_state':'PUBLISHED','description':json.loads(self.cipher.decrypt(row['payload'].encode()))['options']['caption']})
                    if result.get('success') is not True:raise PublicationDenied('Facebook publication outcome requires reconciliation.')
                    # Acceptance is not confirmation: the next provider status poll proves publication.
            return next(p for p in self.snapshot(uid) if p['id']==attempt_id)
        except Exception as error:
            # Preserve ambiguity and never repeat the finish mutation after a lost response.
            with self.store.connection() as db:db.execute("UPDATE publications SET status='unknown',updated=? WHERE id=? AND lease_owner=? AND status NOT IN ('published','failed')",(time.time(),attempt_id,lease_owner))
            self.diagnostics.emit(uid,row['clip_id'],attempt_id,row['platform'],'unknown',code='status_unconfirmed',http_status=getattr(error,'http_status',None))
            raise PublicationDenied('Publication status is pending reconciliation. Do not repeat the upload.') from None
        finally:
            with self.store.connection() as db:db.execute("UPDATE publications SET lease_expires=0,lease_owner='' WHERE id=? AND lease_owner=?",(attempt_id,lease_owner))
    def finishing(self,uid,row,lease_owner):
        with self.store.connection(atomic=True) as db:
            from .owner_showcase import operational_cancellation_revoked
            if operational_cancellation_revoked(db,uid):raise PublicationDenied('Subscription cancellation has ended access.')
            # A reconnect must not move an already prepared clip to a new identity.
            payload=json.loads(self.cipher.decrypt(row['payload'].encode()))
            if row['automation']:self.automation.guard(db,uid,row['clip_id'],row['platform'],json.loads(row['automation']))
            _,_,version=self.credentials(uid,row['platform'])
            if version!=payload['authorizationVersion']:raise PublicationDenied('Upload authorization changed. Reconcile the original destination.')
            return db.execute("UPDATE publications SET status='finishing',finish_started=1,updated=? WHERE id=? AND user_id=? AND lease_owner=? AND lease_expires>? AND finish_started=0",(time.time(),row['id'],uid,lease_owner,time.time())).rowcount==1
    def failed(self,uid,row,lease_owner=None):
        with self.store.connection(atomic=True) as db:
            if lease_owner and not db.execute('SELECT 1 FROM publications WHERE id=? AND lease_owner=? AND lease_expires>?',(row['id'],lease_owner,time.time())).fetchone():return
            db.execute("UPDATE publications SET status='failed',payload=NULL,updated=? WHERE id=? AND user_id=?",(time.time(),row['id'],uid))
            remaining=db.execute("SELECT 1 FROM publications WHERE user_id=? AND clip_id=? AND day=? AND status!='failed'",(uid,row['clip_id'],row['day'])).fetchone()
            if not remaining:db.execute("DELETE FROM clip_capacity WHERE user_id=? AND clip_id=? AND day=? AND status='reserved'",(uid,row['clip_id'],row['day']))

        self.diagnostics.emit(uid,row['clip_id'],row['id'],row['platform'],'failed',code='provider_failed')
