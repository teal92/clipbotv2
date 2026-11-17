"""Plan-change routes reuse session ownership, origin and CSRF validation."""
import stripe
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictBool
from typing import Literal
from .billing import BillingUnavailable
from .network_check import log_billing_failure

class PlanChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    plan:Literal['starter','creator','pro','custom']
    custom:dict[str,StrictInt]|None=None
    quotedMonthlyCents:StrictInt|None=None

class CancellationApproval(BaseModel):
    model_config=ConfigDict(extra='forbid')
    acknowledged:StrictBool

def build_billing_router(billing,current):
    router=APIRouter()
    @router.get('/api/billing/change')
    def status(request:Request):return billing.change_status(current(request)['user_id'])
    @router.post('/api/billing/change/refresh')
    def refresh(request:Request):
        from .billing_changes import refresh
        uid=current(request,True)['user_id']
        try:return refresh(billing,uid)
        except (BillingUnavailable,stripe.StripeError,TimeoutError) as error:
            log_billing_failure(error,'plan_change_status')
            raise HTTPException(503,'Billing status could not be verified. Your previous allowance remains subject to its expiry.')
    @router.post('/api/billing/change')
    def change(data:PlanChange,request:Request):
        uid=current(request,True)['user_id']
        if data.plan=='custom':
            from .pricing import quote
            try:expected=quote(data.plan,data.custom)['monthlyCents']
            except ValueError as error:raise HTTPException(422,str(error))
            if data.quotedMonthlyCents!=expected:raise HTTPException(409,'Custom price changed. Review the monthly quote again.')
        try:return billing.change(uid,data.plan,data.custom)
        except BillingUnavailable as error:raise HTTPException(409,str(error))
        except (stripe.StripeError,TimeoutError) as error:
            log_billing_failure(error,'plan_change')
            raise HTTPException(503,'Billing could not confirm the change. Refresh status before retrying; no extra allowance was granted.')
    @router.post('/api/billing/cancel')
    def cancel(data:CancellationApproval,request:Request):
        uid=current(request,True)['user_id']
        if data.acknowledged is not True:raise HTTPException(422,'Confirm immediate loss of service before canceling.')
        try:return billing.cancel(uid)
        except BillingUnavailable as error:raise HTTPException(409,str(error))
        except (stripe.StripeError,TimeoutError) as error:
            log_billing_failure(error,'cancellation')
            raise HTTPException(503,'Cancellation could not be confirmed. Refresh billing status before retrying.')
    @router.post('/api/billing/portal')
    def portal(request:Request):
        uid=current(request,True)['user_id']
        try:return billing.portal(uid)
        except BillingUnavailable as error:raise HTTPException(409,str(error))
        except (stripe.StripeError,TimeoutError) as error:
            log_billing_failure(error,'portal')
            raise HTTPException(503,'Stripe-hosted billing management is unavailable. Try again later.')
    return router
