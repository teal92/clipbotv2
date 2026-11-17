"""Authoritative proposal calculations. Quotes never activate entitlements."""
from math import ceil

LIMITS={'scouts':(0,40),'streamerFavorites':(0,25),'categoryFavorites':(0,25),'dailyReviews':(12,180)}
STANDARD={'starter':(700,6,0,0,15,20,2000000),'creator':(2500,12,3,3,45,20,6000000),'pro':(6000,30,10,10,120,None,8000000)}

def quote(plan,custom=None):
    if plan in STANDARD:
        if custom is not None:raise ValueError('Custom quantities apply only to Custom.')
        cents,scouts,favorites,categories,reviews,posts,ceiling=STANDARD[plan]
        values={'scouts':scouts,'streamerFavorites':favorites,'categoryFavorites':categories,'dailyReviews':reviews,'postsPerPlatformDaily':posts}
        monthly={'starter':450,'creator':1350,'pro':3600}[plan]
    elif plan=='custom':
        if not isinstance(custom,dict) or set(custom)!=set(LIMITS):raise ValueError('Choose all four custom quantities.')
        for key,(low,high) in LIMITS.items():
            if type(custom[key]) is not int or not low<=custom[key]<=high:raise ValueError('Custom quantities must be whole numbers within slider limits.')
        values=dict(custom)
        raw=700+max(0,custom['scouts']-6)*50+custom['streamerFavorites']*20+custom['categoryFavorites']*20+max(0,custom['dailyReviews']-12)*45
        cents=min(8500,max(1000,((raw+499)//500)*500))
        monthly=custom['dailyReviews']*30
        # Planning ceiling based on the current illustrative review estimate, not a provider price guarantee.
        ceiling=min(12,max(2,ceil(monthly*12/5400)))*1000000
    else:raise ValueError('Choose a listed plan.')
    values['uniqueClipsDaily']=20 if plan in ('starter','creator') else None
    return {'plan':plan,'monthlyCents':cents,'currency':'USD','quantities':values,'monthlyReviews':monthly,'aiCeilingMicros':ceiling,'dailyAiCeilingMicros':250000 if plan=='pro' else 400000 if plan=='custom' else None,'active':False,'pricingVersion':'launch-2026-10-15','notice':'Quote only. Verified payment and owner spending safeguards are required.'}
