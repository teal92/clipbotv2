"""Bound received bytes before JSON parsing, even with chunked transfer."""
from starlette.responses import JSONResponse

class RequestBodyLimit:
    def __init__(self,app,max_bytes=16384,limits=None):
        self.app=app;self.max_bytes=max_bytes;self.limits={'/api/billing/webhook':131072,'/api/worker/analyze':65536,'/api/worker/companion-heartbeat':262144,'/api/account/avatar':196608} if limits is None else limits
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method'] not in ('POST','PUT','PATCH','DELETE'):
            await self.app(scope,receive,send);return
        max_bytes=self.limits.get(scope.get('path'),self.max_bytes)
        chunks=[];size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            chunk=message.get('body',b'');size+=len(chunk)
            if size>max_bytes:
                await JSONResponse({'detail':'Request too large.'},status_code=413)(scope,receive,send);return
            chunks.append(chunk)
            if not message.get('more_body',False):break
        first=True
        async def limited_receive():
            nonlocal first
            if first:
                first=False
                return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        await self.app(scope,limited_receive,send)
