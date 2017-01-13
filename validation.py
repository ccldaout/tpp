# -*- coding: utf-8 -*-

import functools
import os
from tpp.funcutil import prehook_wrapper

VALIDATION_DISABLE = (os.getenv('TPP_VALIDATION_DISABLE') is not None)

#----------------------------------------------------------------------------
#
#----------------------------------------------------------------------------

def keyword(f):
    '''Enforce keyword parameter for optional argument'''
    if VALIDATION_DISABLE:
        return f
    c = f.__code__
    pac = c.co_argcount - len(f.__defaults__)
    fn = f.__name__
    pa = ''.join([s+', ' for s in c.co_varnames[:pac]])

    src = '''def make_wrapper(%s):
    def _%s(%s**keywords):
        return %s(%s**keywords)
    return _%s''' % (fn, fn, pa, fn, pa, fn)
    dic = {}
    eval(compile(src, f.__module__, 'exec'), dic)
    _f = functools.wraps(f)(dic['make_wrapper'](f))

    def make_sig():
        for i, v in enumerate(c.co_varnames[pac:c.co_argcount]):
            yield '%s=%s' % (v, repr(f.__defaults__[i]))
    _f.__doc__ = 'keywords: %s%s' % (', '.join(make_sig()),
                                     '\n \n'+_f.__doc__ if _f.__doc__ else '')
    return _f

#----------------------------------------------------------------------------
#
#----------------------------------------------------------------------------

class Check(object):
    @keyword
    def __init__(self, accepts=(), types=None, min=None, max=None, pred=None):
        self._accepts = accepts if isinstance(accepts, (tuple, list, set, dict)) else (accepts,)
        self._types = types
        self._min = min
        self._max = max
        self._pred = pred

    def __call__(self, key, val):
        if val in self._accepts:
            return
        if (self._accepts and
            self._types is None and self._min is None and
            self._max is None and self._pred is None):
            raise TypeError('Parameter %s must be one of %s' % (key, self._accepts))

        if self._types:
            if not isinstance(val, self._types):
                raise TypeError('Parameter %s require %s, but assigned value %s is not.' %
                                (key, self._types, val))
        if self._min is not None:
            if val < self._min:
                raise TypeError('Assigned value %s for parameter %s is too small.' % (val, key))

        if self._max is not None:
            if val > self._max:
                raise TypeError('Assigned value %s for parameter %s is too big.' % (val, key))

        if self._pred is not None:
            self._pred(key, val)

class _ArgChecker(object):
    def __init__(self, **keywords):
        for key, chk in keywords.items():
            if not isinstance(chk, Check):
                raise TypeError('Parameter of %s must be Check object.' % key)
        self._db = keywords

    def __call__(self, *__args, **params):
        for key, val in params.iteritems():
            if key in self._db:
                self._db[key](key, val)

def parameter(**kws):
    def wrapper(f):
        if VALIDATION_DISABLE:
            return f
        ac = _ArgChecker(**kws)
        return prehook_wrapper(f, ac)
    return wrapper

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []
