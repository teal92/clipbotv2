"""Authenticated profile edits. Passwords are write-only; uploads are decoded locally."""
import base64, binascii, io, re, sqlite3, warnings
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image, ImageOps, UnidentifiedImageError
from .store import normalize_username,UsernameChangeUnavailable

class Profile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username:str=Field(min_length=3,max_length=30)
class PasswordChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    currentPassword:str=Field(min_length=1,max_length=128)
    newPassword:str=Field(min_length=12,max_length=128)
class Avatar(BaseModel):
    model_config=ConfigDict(extra='forbid')
    image:str=Field(max_length=175000)

def safe_avatar(value):
    if not value:return ''
    try:
        raw=base64.b64decode(value,validate=True)
        if len(raw)>131072:raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>4000000 or getattr(image,'n_frames',1)!=1:raise ValueError()
                image.load()
                clean=ImageOps.fit(ImageOps.exif_transpose(image).convert('RGB'),(256,256))
                clean.info.clear();output=io.BytesIO();clean.save(output,format='PNG',optimize=True)
        return 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode('ascii')
    except (ValueError,binascii.Error,UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise ValueError('Choose a JPEG, PNG or WebP image up to 128 KB and 4 million pixels.') from None

def build_account_router(store,current,rate,account):
    router=APIRouter()
    @router.patch('/api/account/profile')
    def profile(data:Profile,request:Request):
        session=current(request,True)
        try:username=normalize_username(data.username);store.update_profile(session['user_id'],username)
        except UsernameChangeUnavailable as error:raise HTTPException(409,str(error)) from None
        except ValueError as error:raise HTTPException(422,str(error)) from None
        except sqlite3.IntegrityError:raise HTTPException(409,'That username is unavailable.') from None
        return account(session)
    @router.put('/api/account/avatar')
    def avatar(data:Avatar,request:Request):
        session=current(request,True);rate(request)
        try:value=safe_avatar(data.image)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        store.update_avatar(session['user_id'],value);return account(session)
    @router.post('/api/account/password')
    def password(data:PasswordChange,request:Request):
        session=current(request,True);rate(request)
        from .password_policy import validate_new_password
        try:validate_new_password(data.newPassword)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if data.currentPassword==data.newPassword:raise HTTPException(422,'Choose a different password.')
        if not store.change_password(session['user_id'],session['token'],data.currentPassword,data.newPassword):raise HTTPException(403,'Your current password is incorrect. No changes were made.')
        return {'ok':True,'message':'Password changed. Other sessions and local workers were disconnected.'}
    return router
