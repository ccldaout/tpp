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

class ArgChecker(object):
    def __init__(self, **keywords):
        self._db = keywords
    def __call__(self, *__args, **params):
        for key, chk in self._db.iteritems():
            if key in params:
                val = params[key]
                if not isinstance(val, chk[0]):
                    raise TypeError('Parameter %s require %s, but assigned value %s is not.' %
                                   (key, chk[0], val))
                # chk: (int, (min, max))
                #      (int, {val, val, ...})
                #      (int, function)
                #      (str, {kw:val, kw:val, ...})
                #      (str, function)
                # check val with chk

def parameter(**kws):
    def wrapper(f):
        if VALIDATION_DISABLE:
            return f
        ac = ArgChecker(**kws)
        return prehook_wrapper(f, ac)
    return wrapper

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []
