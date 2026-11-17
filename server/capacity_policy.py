"""Read-only cost assumptions and proposed capacities; never entitlements."""
from copy import deepcopy
from .pricing import quote,LIMITS
from .claude_connection import MODEL


def planning_policy(ledger=None):
    plans={}
    for name in ('starter','creator','pro'):
        plan=quote(name)
        plans[name]={'dailyReviews':plan['quantities']['dailyReviews'],'monthlyReviews':plan['monthlyReviews'],
                     'dailyAIUSD':plan['dailyAiCeilingMicros']/1000000 if plan['dailyAiCeilingMicros'] is not None else 1,'monthlyAIUSD':plan['aiCeilingMicros']/1000000,'monthlyPriceUSD':plan['monthlyCents']/100}
    proposed=deepcopy(plans)
    for name,daily,monthly in [('starter',30,900),('creator',90,2700)]:proposed[name].update(dailyReviews=daily,monthlyReviews=monthly)
    return {'version':'capacity-planning-2026-10-15-launch-caps','model':MODEL,'includesPrepaid':False,
        'maxInputTokens':8000,'maxOutputTokens':1000,'inputUSDPerMillion':.10,'outputUSDPerMillion':.50,
        'reviewCostUSD':.0013,'reservePerReviewUSD':.002,'maxDailyAIUSD':1,
        'globalDailyUSD':ledger.global_daily/1000000 if ledger else 20,
        'globalMonthlyUSD':ledger.global_monthly/1000000 if ledger else 400,
        'plans':plans,'proposedPlans':proposed,
        'custom':{'minDailyReviews':LIMITS['dailyReviews'][0],'maxDailyReviews':LIMITS['dailyReviews'][1],
                  'monthDays':30,'minimumMonthlyAIUSD':2,'allowancePerMonthlyReviewUSD':12/5400,'maximumMonthlyAIUSD':12,'dailyAIUSD':.4,
                  'referenceQuote':quote('custom',{key:bounds[1] for key,bounds in LIMITS.items()})}}
