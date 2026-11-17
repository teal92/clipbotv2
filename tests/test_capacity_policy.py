import json
import pytest
from server.pricing import quote


@pytest.mark.parametrize('plan,daily,monthly,ceiling',[('starter',30,900,2000000),('creator',90,2700,6000000)])
def test_proposed_reviews_double_without_activating_price_or_budget_changes(plan,daily,monthly,ceiling):
    from server.capacity_policy import planning_policy
    policy=planning_policy();result=policy['proposedPlans'][plan]
    assert result['dailyReviews']==daily and result['monthlyReviews']==monthly
    assert result['monthlyAIUSD']==ceiling/1000000
    assert quote(plan)['quantities']['dailyReviews']==(15 if plan=='starter' else 45)


def test_capacity_policy_matches_authoritative_plans_without_customer_data():
    from server.capacity_policy import planning_policy
    from server.claude_connection import MODEL
    result=planning_policy()
    assert result['model']==MODEL and result['reviewCostUSD']==pytest.approx(.0013)
    assert result['reservePerReviewUSD']==.002 and result['includesPrepaid'] is False
    for name in ('starter','creator','pro'):
        plan=quote(name);expected=result['plans'][name]
        assert expected['dailyReviews']==plan['quantities']['dailyReviews']
        assert expected['monthlyReviews']==plan['monthlyReviews']
        assert expected['monthlyAIUSD']==plan['aiCeilingMicros']/1000000
    assert not any(k in json.dumps(result).lower() for k in ('password','customer_id','api_key'))
    assert result['custom']['referenceQuote']==quote('custom',{'scouts':40,'streamerFavorites':25,'categoryFavorites':25,'dailyReviews':180})
