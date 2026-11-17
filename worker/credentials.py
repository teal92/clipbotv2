"""Windows user-bound DPAPI device storage; never plaintext credentials."""
import ctypes,json,os,sys
from pathlib import Path

def crypt(data,decrypt=False):
    if os.name!='nt':raise RuntimeError('Secure persistent device storage requires Windows.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));result=Blob()
    library=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    function=library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)];function.restype=wintypes.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):raise RuntimeError('Secure device storage failed.')
    try:return ctypes.string_at(result.data,result.size)
    finally:kernel.LocalFree(result.data)

def save(path,origin,token):
    if not isinstance(token,str) or not 20<=len(token)<=100:raise ValueError('Invalid device credential.')
    if sys.platform!='win32':
        from .platforms.secrets import save as native_save
        return native_save(path,origin,token)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    encrypted=crypt(json.dumps({'origin':origin,'token':token}).encode())
    temporary=path.with_suffix('.tmp');temporary.write_bytes(encrypted);temporary.replace(path)

def load(path,origin):
    if sys.platform!='win32':
        try:
            from .platforms.secrets import load as native_load
            token=native_load(path,origin)
        except Exception:raise RuntimeError('Unlock your login keychain or desktop keyring, then reconnect the companion.') from None
        return token if isinstance(token,str) and 20<=len(token)<=100 else None
    try:
        path=Path(path)
        if not path.is_file() or path.stat().st_size>8192:return None
        value=json.loads(crypt(path.read_bytes(),True));token=value.get('token')
        return token if value.get('origin')==origin and isinstance(token,str) and 20<=len(token)<=100 else None
    except Exception:return None

def delete(path,origin):
    if sys.platform!='win32':
        from .platforms.secrets import delete as native_delete
        return native_delete(path,origin)
    Path(path).unlink(missing_ok=True)
