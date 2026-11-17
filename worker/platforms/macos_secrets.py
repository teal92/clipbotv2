"""Generic passwords through Apple's native Security framework, in process."""
import ctypes as C

SERVICE = b'com.yourcompany.clipbot.companion'
NOT_FOUND = -25300


class Keychain:
    def __init__(self):
        self.security = C.CDLL('/System/Library/Frameworks/Security.framework/Security')
        self.core = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        pointer, size, text = C.c_void_p, C.c_uint32, C.c_char_p
        signatures = {
            'SecKeychainFindGenericPassword': [pointer, size, text, size, text, C.POINTER(size), C.POINTER(pointer), C.POINTER(pointer)],
            'SecKeychainAddGenericPassword': [pointer, size, text, size, text, size, pointer, C.POINTER(pointer)],
            'SecKeychainItemModifyAttributesAndData': [pointer, pointer, size, pointer],
            'SecKeychainItemDelete': [pointer],
            'SecKeychainItemFreeContent': [pointer, pointer],
        }
        for name, args in signatures.items():
            function = getattr(self.security, name)
            function.argtypes, function.restype = args, C.c_int32
        self.core.CFRelease.argtypes, self.core.CFRelease.restype = [pointer], None

    def _find(self, key):
        account = key.encode('ascii')
        length, data, item = C.c_uint32(), C.c_void_p(), C.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(None, len(SERVICE), SERVICE, len(account), account, C.byref(length), C.byref(data), C.byref(item))
        if status == NOT_FOUND:
            return None, None
        if status:
            raise RuntimeError('Login keychain is unavailable.')
        try:
            if length.value > 1024:
                raise RuntimeError('Invalid keychain entry.')
            value = C.string_at(data, length.value).decode('utf-8')
        except Exception:
            if item.value:
                self.core.CFRelease(item)
            raise
        finally:
            if data.value:
                self.security.SecKeychainItemFreeContent(None, data)
        return value, item

    def get(self, key):
        value, item = self._find(key)
        if item:
            self.core.CFRelease(item)
        return value

    def put(self, key, value):
        _, item = self._find(key)
        raw, account = value.encode('utf-8'), key.encode('ascii')
        try:
            if item:
                status = self.security.SecKeychainItemModifyAttributesAndData(item, None, len(raw), raw)
            else:
                status = self.security.SecKeychainAddGenericPassword(None, len(SERVICE), SERVICE, len(account), account, len(raw), raw, None)
            if status:
                raise RuntimeError('Login keychain could not store the credential.')
        finally:
            if item:
                self.core.CFRelease(item)

    def remove(self, key):
        _, item = self._find(key)
        if item:
            try:
                if self.security.SecKeychainItemDelete(item):
                    raise RuntimeError('Login keychain could not remove the credential.')
            finally:
                self.core.CFRelease(item)
