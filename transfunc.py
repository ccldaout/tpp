# -*- coding: utf-8 -*-

import copy_reg
import sys
import types
import weakref
import __builtin__

#----------------------------------------------------------------------------
#                 function packager for transport to remote
#----------------------------------------------------------------------------

_inhibit_builtins = set([
    '__import__', 'compile', 'dir', 'eval', 'execfile', 'float',
    'input', 'open', 'raw_input', 'reload'])

_permit_builtins = set(__builtin__.__dict__.keys()) - _inhibit_builtins

_permit_modules = set([
    'datetime', 'heapq', 'bisect', 'array', 'numbers', 'math', 'cmath',
    'random', 'itertools', 'functools', 'operator', 'hashlib', 'time'])

def _code_new(*args):
    return types.CodeType(*args)

def _code_reduce(code):
    def code_iter(code):
        # Order of attribute names in _code_attrs must be same as order of arguments
        # of types.CodeType constructor.
        _code_attrs = ('co_argcount', 'co_nlocals', 'co_stacksize', 'co_flags', 'co_code',
                       'co_consts', 'co_names', 'co_varnames', 'co_filename', 'co_name',
                       'co_firstlineno', 'co_lnotab', 'co_freevars', 'co_cellvars')
        for n in _code_attrs:
            yield getattr(code, n)
    return (_code_new, tuple(code_iter(code)))

copy_reg.pickle(types.CodeType, _code_reduce)

class _FuncAttrs(object):
    def __new__(cls, f=None, gname=None):
        self = super(_FuncAttrs, cls).__new__(cls)
        if not f:
            return self
        self._code = f.__code__
        self._name = f.__name__
        self._defaults = f.__defaults__
        self._dict = f.__dict__
        self._gname = gname
        return self

    def gen(self, gdic):
        f = types.FunctionType(self._code, gdic, self._name, self._defaults)
        f.__dict__ = self._dict
        gdic[self._gname] = f
        return f

class _Package(object):
    def __new__(cls, f=None, gname=None):
        self = super(_Package, cls).__new__(cls)
        if not f:
            return self
        self._g_builtins = set()
        self._g_modules = set()
        self._g_data = {}
        self._funcattrs = []
        self._covered = set()
        self._setup_func(f, gname if gname else f.__name__)
        del self._covered
        return self

    def _setup_code(self, f, code):
        for n in code.co_names:
            if n in f.__globals__:
                v = f.__globals__[n]
                if isinstance(v, types.FunctionType):
                    self._setup_func(v, n)
                elif isinstance(v, types.ModuleType):
                    if n in _permit_modules:
                        self._g_modules.add(n)
                    else:
                        raise TypeError('Invalid module: %s' % n)
                else:
                    self._check_data(v)
                    self._g_data[n] = v
            elif n in __builtin__.__dict__:
                if n in _permit_builtins:
                    self._g_builtins.add(n)
                else:
                    raise TypeError('Invalid builtin: %s' % n)
            else:
                raise TypeError('Invalid name: %s' % n)
        for c in code.co_consts:
            if isinstance(c, types.CodeType):
                self._setup_code(f, c)

    def _setup_func(self, f, gname):
        if f in self._covered:
            return
        self._covered.add(f)
        self._setup_code(f, f.__code__)
        self._funcattrs.append(_FuncAttrs(f, gname))

    def _check_data(self, v):
        if isinstance(v, (tuple, list)):
            for vv in v:
                self._check_data(vv)
        elif isinstance(v, dict):
            for k, vv in v:
                self._check_data(k)
                self._check_data(vv)
        elif not isinstance(v, (int, long, float, basestring, bytearray)):
            raise TypeError('Not permitted: %s, %s', v, type(v))

    def unpack(self):
        gdic = {}
        for n in self._g_builtins:
            if n in _permit_builtins:
                gdic[n] = getattr(__builtin__, n)
        for n in self._g_modules:
            if n in _permit_modules:
                if not hasattr(sys.modules, n):
                    __import__(n)
                gdic[n] = sys.modules[n]
        gdic.update(self._g_data)
        for fattr in self._funcattrs:
            f = fattr.gen(gdic)
        return f

def _unpack(fpkg):
    return fpkg.unpack()

class pack(object):
    __slots__ = ('_funcpkg',)
    __cache = weakref.WeakKeyDictionary()

    def __init__(self, f):
        if f in self.__cache:
            self._funcpkg = self.__cache[f]
        else:
            pkg = _Package(f, f.__name__)
            self.__cache[f] = pkg
            self._funcpkg = pkg

    def __reduce__(self):
        return (_unpack, (self._funcpkg,))

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = ()
