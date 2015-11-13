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

def no_except(func, ret_if_exc=None):
    def _f(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            if os.getenv('TPP_EXC_DEBUG'):
                traceback.print_exc()
            return ret_if_exc
    return _f

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

class Delegate(object):
    __slots__ = ('_funcs',)
    def __new__(cls):
        self = super(Delegate, cls).__new__(cls)
        self._funcs = []
        return self

    def __iadd__(self, func):
        self._funcs.append(func)
        return self

    def __call__(self, *args, **kwargs):
        for f in self._funcs:
            f(*args, **kwargs)

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
    _cond = threading.Condition()
    _key = 0
    _mbox = {}

    def reserve(self, key = None):
        with self._cond:
            cls = type(self)
            if key is None:
                cls._key += 1
                key = cls._key
            else:
                if key in self._mbox:
                    raise RuntimeError("Specified key '%s' is already used." % key)
                if cls._key < key:
                    cls._key = key
            self._mbox[key] = None
    
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

if __name__ == '__main__':
    pass
