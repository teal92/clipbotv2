from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from .client_ip import client_ip
from .site_visitors import SiteVisitors

class VisitorPulse(BaseModel):
    model_config=ConfigDict(extra='forbid')
    visitId:str=Field(pattern=r'^[a-f0-9]{32}$',max_length=32)

def visitor_router(store):
    visitors=SiteVisitors(store);router=APIRouter()
    @router.post('/api/visitor-presence')
    def pulse(data:VisitorPulse,request:Request):
        visitors.pulse(data.visitId,client_ip(request),request.headers.get('user-agent',''),
                       privacy=request.headers.get('dnt')=='1' or request.headers.get('sec-gpc')=='1')
        return {'ok':True}
    return router,visitors
