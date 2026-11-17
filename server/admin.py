"""Owner metrics expose aggregate counts only; never credentials or revenue."""
import argparse,json,os,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from .store import Store
from .metric_scope import customer_scope,plan_counts

BETA_VERSION='beta-feedback-v1'
DEV_EMAIL='clipbot-local-development@example.invalid'

def contribution_series(db,period,now):
    if period not in ('day','week','month','year','all'):raise ValueError('Choose day, week, month, year or all.')

    current=datetime.fromtimestamp(now,timezone.utc);today=current.replace(hour=0,minute=0,second=0,microsecond=0)
    if period=='all':
        earliest=db.execute('SELECT MIN(created) FROM shared_feedback WHERE created>=0 AND created<=?',(now,)).fetchone()[0]
        first=datetime.fromtimestamp(earliest,timezone.utc).year if earliest is not None else current.year
        width=max(1,(current.year-first+32)//32)
        years=list(range(first,current.year+1,width))
        keys=[str(y) if width==1 else str(y)+'-'+str(min(y+width-1,current.year)) for y in years]
        counts={key:0 for key in keys}
        for year,count in db.execute("SELECT strftime('%Y',created,'unixepoch'),COUNT(*) FROM shared_feedback WHERE created>=0 AND created<=? GROUP BY 1",(now,)):
            counts[keys[(int(year)-first)//width]]+=count
        return {'total':sum(counts.values()),'target':1000,'period':'all','timezone':'UTC','supportedPeriods':['day','week','month','year','all'],
                'buckets':[{'key':key,'count':counts[key]} for key in keys],'collectionEnabled':False,'meaning':'All recorded shared contributions, grouped by year; older histories use multi-year buckets. Shared collection is paused.'}
    if period=='year':
        month=current.year*12+current.month-1
        starts=[datetime((month-i)//12,(month-i)%12+1,1,tzinfo=timezone.utc) for i in range(11,-1,-1)]
        keys=[value.strftime('%Y-%m') for value in starts];pattern='%Y-%m';start=starts[0]
        end=datetime((month+1)//12,(month+1)%12+1,1,tzinfo=timezone.utc)
    else:
        count={'day':24,'week':7,'month':30}[period]
        start=today if period=='day' else today-timedelta(days=count-1)
        starts=[start+timedelta(hours=i) if period=='day' else start+timedelta(days=i) for i in range(count)]
        pattern='%Y-%m-%dT%H:00Z' if period=='day' else '%Y-%m-%d';keys=[value.strftime(pattern) for value in starts]
        end=today+timedelta(days=1)
    counts={row[0]:row[1] for row in db.execute("SELECT strftime(?,created,'unixepoch'),COUNT(*) FROM shared_feedback WHERE created>=? AND created<? GROUP BY 1",(pattern,start.timestamp(),min(end.timestamp(),now+0.000001)))}
    total=db.execute('SELECT COUNT(*) FROM shared_feedback WHERE created<=?',(now,)).fetchone()[0]
    return {'supportedPeriods':['day','week','month','year','all'],'total':total,'target':1000,'period':period,'timezone':'UTC','buckets':[{'key':key,'count':counts.get(key,0)} for key in keys],'collectionEnabled':False,'meaning':'Shared learning feedback received across ClipBot. Personal review notes remain on customer hardware. Shared collection is paused; these counts do not measure training accuracy.'}


def metrics(store,period='week',now=None):
    now=time.time() if now is None else now
    sql,args,owner_configured=customer_scope()
    eligible=' IN (SELECT id FROM customer_users)'
    with store.connection() as db:
        # Legacy feedback is deliberately anonymous, so it cannot prove customer origin.
        contributions=contribution_series(db,period,now)
        contributions['excludedUnattributed']=contributions['total']
        contributions['total']=0
        for bucket in contributions['buckets']:bucket['count']=0
        contributions['meaning']='Customer-only feedback. Unattributed historical records are excluded. Shared collection is paused; counts do not measure AI accuracy.'
        users=db.execute(sql+'SELECT COUNT(*) FROM customer_users',args).fetchone()[0]
        plans=plan_counts(db,sql,args,now)
        active=db.execute(sql+'SELECT COUNT(DISTINCT s.user_id) FROM session_presence p JOIN sessions s ON s.token=p.token WHERE p.last_seen>? AND s.expires>? AND s.user_id'+eligible,(*args,now-120,now)).fetchone()[0]
        workers=db.execute(sql+'SELECT COUNT(DISTINCT user_id) FROM worker_devices WHERE expires>? AND last_seen>? AND user_id'+eligible,(*args,now,now-90)).fetchone()[0]
        tokens=db.execute(sql+"SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),COUNT(*) FROM jobs WHERE state='settled' AND user_id"+eligible,args).fetchone()
        participants=db.execute(sql+'SELECT COUNT(*) FROM beta_acceptance WHERE version=? AND user_id'+eligible,(*args,BETA_VERSION)).fetchone()[0]
        posts={platform:0 for platform in ('tiktok','instagram','facebook')}
        publishing=bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='publications'").fetchone())
        if publishing:
            for row in db.execute(sql+"SELECT platform,COUNT(*) FROM publications WHERE status='published' AND user_id"+eligible+' GROUP BY platform',args):
                if row[0] in posts:posts[row[0]]=row[1]
        scouts=0
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pipeline_jobs'").fetchone():
            scouts=db.execute(sql+"SELECT COUNT(*) FROM pipeline_jobs WHERE stage='capturing' AND updated>? AND user_id"+eligible,(*args,now-90)).fetchone()[0]
    return {'scope':'global','metricsScope':'customers_only','ownerExclusionConfigured':owner_configured,
            'source':'ClipBot service · customer accounts only; owner/test accounts excluded',
            'customersByPlan':plans,'customersWithoutActivePlan':users-sum(plans.values()),
            'contributions':contributions,'generatedAt':now,'registeredUsers':users,'activeUsers':active,
            'connectedWorkers':workers,'inputTokens':tokens[0],'outputTokens':tokens[1],'completedReviews':tokens[2],
            'sharedDecisions':0,'approvedDecisions':0,'rejectedDecisions':0,'feedbackReasons':{},
            'platformPosts':posts,'publishingAvailable':publishing,'activeScouts':scouts,'activityWindowSeconds':120,
            'refreshSeconds':15,'sharedUpdatesEnabled':False,'learning':{'decisionTarget':1000,'betaParticipants':participants,
            'participantTarget':10,'reasonCoverage':0,'validationAvailable':False,'precision':None,'recall':None,'agreement':None,'releasedUpdates':None}}


def main():
    parser=argparse.ArgumentParser(description='Look up your existing owner account ID. Does not grant permissions.')
    parser.add_argument('--owner-email',required=True)
    args=parser.parse_args()
    path=Path(os.getenv('CLIPBOT_DB_PATH',str(Path(__file__).resolve().parent/'data'/'clipbot.db')))
    if not path.is_file():raise SystemExit('Account database not found.')
    store=Store(path)
    with store.connection() as db:row=db.execute('SELECT id FROM users WHERE email=? AND email!=?',(args.owner_email.strip().lower(),DEV_EMAIL)).fetchone()
    if not row:raise SystemExit('Existing account not found. Sign in with your owner account first.')
    print(row[0])

if __name__=='__main__':main()
