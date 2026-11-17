"""Connection readiness without credentials, platform calls, or fake OAuth success."""
PLATFORMS=(('twitch','Twitch','monitoring'),('kick','Kick','monitoring'),('tiktok','TikTok','publishing'),('instagram','Instagram','publishing'),('facebook','Facebook','publishing'))

def connection_status(store,uid,oauth=None):
    return {'workerConnected':store.worker_connected(uid),'serviceConnected':True,'platforms':[{'id':key,'name':name,'purpose':purpose,'connected':False,'authorizationAvailable':False,'status':'integration_pending',**(oauth.status(uid,key) if oauth else {})} for key,name,purpose in PLATFORMS],'message':'Connect through official platform sign-in. Publishing and local processing readiness are checked separately.'}
