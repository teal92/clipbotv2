"""Desktop Secret Service via the distribution-provided libsecret ABI."""
import ctypes as C


class Attribute(C.Structure):
    _fields_ = [('name', C.c_char_p), ('type', C.c_int)]


class Schema(C.Structure):
    _fields_ = [('name', C.c_char_p), ('flags', C.c_int), ('attributes', Attribute * 32), ('reserved', C.c_int), *[(f'reserved{i}', C.c_void_p) for i in range(1, 8)]]


class SecretService:
    def __init__(self):
        # Use the OS package loader; never search the working directory or run a shell.
        self.lib = C.CDLL('libsecret-1.so.0')
        self.glib = C.CDLL('libglib-2.0.so.0')
        self.schema = Schema()
        self.schema.name = b'com.yourcompany.ClipBotCompanion'
        self.schema.attributes[0] = Attribute(b'account', 0)
        schema, error = C.POINTER(Schema), C.POINTER(C.c_void_p)
        self.lib.secret_password_store_sync.argtypes = [schema, C.c_char_p, C.c_char_p, C.c_char_p, C.c_void_p, error]
        self.lib.secret_password_store_sync.restype = C.c_int
        for name in ('secret_password_lookup_sync', 'secret_password_clear_sync'):
            getattr(self.lib, name).argtypes = [schema, C.c_void_p, error]
        self.lib.secret_password_lookup_sync.restype = C.c_void_p
        self.lib.secret_password_clear_sync.restype = C.c_int
        self.lib.secret_password_free.argtypes = [C.c_void_p]
        self.lib.secret_password_free.restype = None
        self.glib.g_error_free.argtypes = [C.c_void_p]
        self.glib.g_error_free.restype = None

    def _call(self, name, key, value=None):
        error = C.c_void_p()
        args = [C.byref(self.schema)]
        if value is not None:
            args.extend([b'default', b'ClipBot Companion', value.encode('utf-8')])
        args.extend([None, C.byref(error), C.c_char_p(b'account'), C.c_char_p(key.encode('ascii')), C.c_void_p()])
        result = getattr(self.lib, name)(*args)
        if error.value:
            self.glib.g_error_free(error)
            raise RuntimeError('Desktop keyring is unavailable or locked.')
        return result

    def put(self, key, value):
        if not self._call('secret_password_store_sync', key, value):
            raise RuntimeError('Desktop keyring could not store the credential.')

    def get(self, key):
        pointer = self._call('secret_password_lookup_sync', key)
        if not pointer:
            return None
        try:
            raw = C.string_at(pointer)
            if len(raw) > 1024:
                raise RuntimeError('Invalid desktop keyring entry.')
            return raw.decode('utf-8')
        finally:
            self.lib.secret_password_free(pointer)

    def remove(self, key):
        self._call('secret_password_clear_sync', key)
