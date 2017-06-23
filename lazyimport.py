# -*- coding: utf-8 -*-

import os
import sys
import types as types
from threading import Lock, RLock

_DEBUG = bool(os.getenv('TPP_LAZYIMPORT'))

class LazyModule(types.ModuleType):

    def __new__(cls, name, lazyfinder=None):
        if _DEBUG:
            print '[ lazyimport ] -lazy-', name
        self = super(LazyModule, cls).__new__(cls, name, '')
        self.__lock = RLock()
        self.__loaded = False
        self.__lazyfinder = lazyfinder
        return self

    def __init__(self, name, *args, **kwargs):
        super(LazyModule, self).__init__(name, '')

    def __import(self, attr):
        self.__loaded = True
        name = self.__name__
        if self.__lazyfinder:
            self.__lazyfinder.remove(name)
        if name in sys.modules:
            del sys.modules[name]
        if _DEBUG:
            print ('[ lazyimport ] import %s (access to %s)' % (name, attr))
        m = __import__(name, globals(), locals(), [name.split('.')[-1]])
        self.__dict__.update(m.__dict__)

    def __getattribute__(self, attr):
        if attr == '__dict__':
            with self.__lock:
                if not self.__loaded:
                    self.__import(attr)
        return super(LazyModule, self).__getattribute__(attr)

    def __getattr__(self, attr):
        with self.__lock:
            if not self.__loaded:
                self.__import(attr)
        return super(LazyModule, self).__getattribute__(attr)

class LazyLoader(object):
    _slots_ = ('_lazyfinder')

    def __init__(self, lazyfinder):
        self._lazyfinder = lazyfinder

    def load_module(self, name):
        if name not in sys.modules:
            m = LazyModule(name, self._lazyfinder)
            sys.modules[name] = m
        return sys.modules[name]
        
class LazyFinder(object):
    _slots_ = ('_lock', '_mods', '_roots', '_excepts')

    def __init__(self):
        self._lock = Lock()
        self._mods = set()
        self._roots = set()
        self._excepts = set()

    def register(self, modname):
        with self._lock:
            self._mods.add(modname)

    def register_root(self, rootmod):
        with self._lock:
            self._roots.add(rootmod)
            self._mods.add(rootmod)

    def remove(self, modname):
        with self._lock:
            self._excepts.add(modname)
            if modname in self._mods:
                self._mods.remove(modname)

    def find_module(self, modname, paths):
        def check():
            if paths is None:
                return False
            lastname = modname.split('.')[-1]
            for p in paths:
                for sfx in ['.py', '.pyc', '.so']:
                    if os.path.exists(os.path.join(p, lastname + sfx)):
                        return True
                if os.path.isdir(os.path.join(p, lastname)):
                    return True
            return False
        def do_lazy():
            if modname in self._excepts:
                return False
            if modname in self._mods:
                return check()
            for r in self._roots:
                rz = len(r)
                if modname[:rz] == r and modname[rz] == '.':
                    return check()
            return False
        with self._lock:
            if do_lazy():
                return LazyLoader(self)
        return None

_lazyfinder = LazyFinder()
register = _lazyfinder.register
register_root = _lazyfinder.register_root

sys.meta_path.append(_lazyfinder)

__all__ = ['register']
