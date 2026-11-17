"""Authenticated customer settings; no client-supplied phase or eligibility."""
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictBool
from .davey import DaveyStore


class DaveyChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    settings:dict
    revision:StrictInt=Field(ge=0)

class DaveyReset(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=0)
    confirmed:StrictBool


def build_davey_router(store,current):
    router=APIRouter();davey=DaveyStore(store)
    @router.get('/api/davey/progression')
    def status(request:Request):
        return davey.status(current(request)['user_id'])
    @router.put('/api/davey/progression')
    def save(data:DaveyChange,request:Request):
        uid=current(request,True)['user_id']
        try:return davey.save(uid,data.settings,expected_revision=data.revision)
        except ValueError as error:raise HTTPException(409,str(error)) from None
    @router.post('/api/davey/reset')
    def reset(data:DaveyReset,request:Request):
        uid=current(request,True)['user_id']
        if not data.confirmed:raise HTTPException(409,'Confirm the personal-memory reset first.')
        try:return davey.reset(uid,data.revision)
        except ValueError as error:raise HTTPException(409,str(error)) from None
    return router,davey
