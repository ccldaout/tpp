# -*- coding: utf-8 -*-

import os
import os.path
import threading
import traceback
import time

#----------------------------------------------------------------------------
#                              Small utilities
#----------------------------------------------------------------------------

def alignP2(_z, p2):
    return ((_z | (p2-1)) + 1)

class _Printer(object):
    __slots__ = ('print_name',)
    _lock = threading.Lock()

    def __init__(self):
        self.print_name = os.getenv('TPP_PR_NAME')

    def __call__(self, fmt, *args):
        if self.print_name:
            fmt = threading.current_thread().name + ': ' +fmt
        s = fmt % args
        with self._lock:
            print s

pr = _Printer()

class no_abort(object):
    def __init__(self):
        self._exc_simple = True
        self._exc_expect = 'Exception'
    def __call__(self, exc_simple=True, expect='Exception'):
        self._exc_simple = exc_simple
        self._exc_expect = expect
        return self
    def __enter__(self):
        pass
    def __exit__(self, exc_type, exc_value, exc_traceback):
        print '<<< expect:', self._exc_expect
        if exc_type is not None:
            if self._exc_simple:
                print '>>> %s: %s' % (exc_type.__name__, exc_value)
            else:
                traceback.print_exc()
        else:
            print '>>> no error'
        return True

no_abort = no_abort()

def no_except(func, ret_if_exc=None):
    def _f(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            if os.getenv('TPP_EXC_DEBUG'):
                traceback.print_exc()
            return ret_if_exc
    return _f

class SimpleProperty(object):
    def __init__(self, attr, encoder=None, decoder=None):
        self._enc = encoder if encoder else lambda v:v
        self._dec = decoder if decoder else lambda v:v
        self._attr = attr

    def __get__(self, obj, cls):
        return self._dec(getattr(obj, self._attr))

    def __set__(self, obj, val):
        return setattr(obj, self._attr, self._enc(val))

class Delegate(object):
    __slots__ = ('_funcs',)

    def __new__(cls):
        self = super(Delegate, cls).__new__(cls)
        self._funcs = []
        return self

    def __iadd__(self, func):
        if not func in self._funcs:
            self._funcs.append(func)
        return self

    def __isub__(self, func):
        if func in self._funcs:
            self._funcs.remove(func)
        return self

    def __contains__(self, func):
        return func in self._funcs

    def __nonzero__(self):
        return bool(self._funcs)

    def __len__(self):
        return len(self._funcs)

    def __iter__(self):
        return iter(self._funcs)

    def __call__(self, *args, **kwargs):
        for f in self._funcs:
            f(*args, **kwargs)

class Counter(object):
    __slots__ = ('_v', '_lock')

    def __new__(cls):
        self = super(Counter, cls).__new__(cls)
        self._v = 0
        self._lock = threading.Lock()
        return self

    def __call__(self):
        with self._lock:
            self._v += 1
            return self._v

class Null(object):
    def __nonzero__(self):
        return False
    def __call__(self, *args):
        return self
    def __getattr__(self, name):
        return self
    def __setattr__(self, name, val):
        pass
    def __getitem__(self, key):
        return self
    def __setitem__(self, key, val):
        pass
    def __contains__(self, key):
        return False
    def __iter__(self):
        return iter([])

Null = Null()

class Bomb(object):
    __slots__ = ('_exc',)

    def __new__(cls, exc):
        self = super(Bomb, cls).__new__(cls)
        super(Bomb, self).__setattr__('_exc', exc)
        return self
    def __nonzero__(self):
        raise self._exc
    def __call__(self, *args):
        raise self._exc
    def __getattr__(self, name):
        raise self._exc
    def __setattr__(self, name, val):
        raise self._exc
    def __getitem__(self, key):
        raise self._exc
    def __setitem__(self, key, val):
        raise self._exc
    def __contains__(self, key):
        raise self._exc
    def __iter__(self):
        raise self._exc

class nameddict(dict):
    def __getattribute__(self, name):
        try:
            return super(nameddict, self).__getattribute__('__getitem__')(name)
        except:
            return super(nameddict, self).__getattribute__(name)

#----------------------------------------------------------------------------
#
#----------------------------------------------------------------------------

class fn(object):
    @staticmethod
    def eval(path):
        return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))

    @staticmethod
    def add_suffix(path, suffix):
        if not path.endswith(suffix):
            path = path + suffix
        return path

    @staticmethod
    def find(name, env, alt_list=None):
        def _find(name, ls):
            for d in ls:
                d = os.path.expanduser(os.path.expandvars(d))
                path = os.path.join(d, name)
                if os.path.exists(path):
                    return os.path.abspath(path)
            return None
        if '/' in name:
            return fn.eval(name)
        path = None
        if env:
            ls = os.getenv(env)
            if ls:
                path = _find(name, ls.split(':'))
        if not path:
            if isinstance(alt_list, (tuple, list)):
                path = _find(name, alt_list)
            elif isinstance(alt_list, str):
                path = _find(name, alt_list.split(':'))
        return path

#----------------------------------------------------------------------------
#                     Message exchanger by onetime key
#----------------------------------------------------------------------------

class OnetimeMsgBox(object):

    def __new__(cls):
        self = super(OnetimeMsgBox, cls).__new__(cls)
        self._cond = threading.Condition()
        self._key = 0
        self._mbox = {}
        return self

    def __iter__(self):
        return self._mbox.iteritems()

    def reserve(self, key = None):
        with self._cond:
            if key is None:
                self._key += 1
                key = self._key
            else:
                if key in self._mbox:
                    raise RuntimeError("Specified key '%s' is already used." % key)
                if self._key < key:
                    self._key = key
            self._mbox[key] = None
            return key
    
    def cancel(self, key):
        with self._cond:
            self._mbox.pop(key, None)

    def post(self, key, value, strict=False):
        with self._cond:
            if key in self._mbox:
                self._mbox[key] = value
                self._cond.notify_all()
            elif strict:
                raise KeyError("Specified key '%s' is not reserved." % key)

    def wait(self, key, tmo_s = None):
        if tmo_s is None:
            tmo_s = (3600*24*365*10)
        lim_tv = time.time() + tmo_s
        with self._cond:
            while self._mbox[key] is None:
                self._cond.wait(tmo_s)
                now_tv = time.time()
                if now_tv >= lim_tv:
                    return None		# timeout
                tmo_s = lim_tv - now_tv
            return self._mbox.pop(key)

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []
