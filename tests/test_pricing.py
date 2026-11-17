import pytest
from server.pricing import quote

def test_standard_quotes():
    assert quote('starter')['monthlyCents']==700
    assert quote('creator')['monthlyCents']==2500
    assert quote('pro')['monthlyCents']==6000
    with pytest.raises(TypeError):quote('starter',patreon_verified=True)
    assert quote('starter')['monthlyCents']==700
    assert quote('starter')['active'] is False

def test_custom_limits():
    minimum={'scouts':0,'streamerFavorites':0,'categoryFavorites':0,'dailyReviews':12}
    maximum={'scouts':40,'streamerFavorites':25,'categoryFavorites':25,'dailyReviews':180}
    assert quote('custom',minimum)['monthlyCents']==1000
    assert quote('custom',maximum)['monthlyCents']==8500
    assert quote('custom',maximum)['monthlyReviews']==5400
    assert quote('custom',maximum)['aiCeilingMicros']==12000000
    for key,value in maximum.items():
        with pytest.raises(ValueError):quote('custom',{**maximum,key:value+1})
        with pytest.raises(ValueError):quote('custom',{**maximum,key:True})
    with pytest.raises(ValueError):quote('custom',{**maximum,'price':1})
    with pytest.raises(ValueError):quote('missing')


def test_beta_posting_allowance_keeps_ai_limits():
    for plan,limit,reviews in [('starter',20,15),('creator',20,45),('pro',None,120)]:
        result=quote(plan)
        assert result['quantities']['uniqueClipsDaily']==limit
        assert result['quantities']['dailyReviews']==reviews
    custom={'scouts':40,'streamerFavorites':25,'categoryFavorites':25,'dailyReviews':180}
    assert quote('custom',custom)['monthlyCents']==8500
    assert quote('custom',custom)['quantities']['uniqueClipsDaily'] is None
