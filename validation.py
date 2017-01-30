# -*- coding: utf-8 -*-

import functools
import os
from tpp.funcutil import prehook_wrapper, Symbols

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

    pv = c.co_varnames[:pac]
    syms = Symbols(pv)
    fn = syms.uniq(f.__name__)
    gn = syms.uniq('_' + f.__name__)
    pa = ''.join([s+', ' for s in pv])
    kw = syms.uniq('keywords')

    src = '''def make_wrapper(%s):
    def %s(%s**%s):
        return %s(%s**%s)
    return %s''' % (fn, gn, pa, kw, fn, pa, kw, gn)
    dic = {}
    eval(compile(src, '<@keyword>', 'exec'), dic)
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
    __slots__ = tuple('_accepts_only:_accepts:_types:_min:_max:_inf:_sup:'
                      '_pred:_normalizer:_dim:_doc'.split(':'))

    @keyword
    def __init__(self, accepts=(), types=None, min=None, max=None, inf=None, sup=None,
                 pred=None, normalizer=None, dim=0, doc=''):
        self._accepts = accepts if isinstance(accepts, (tuple, list, set, dict)) else (accepts,)
        self._accepts_only = (self._accepts and
                              all([_ is None for _ in [types, min, max, inf, sup, pred]]))
        self._types = types
        self._min = min
        self._max = max
        self._inf = inf
        self._sup = sup
        self._pred = pred
        self._normalizer = normalizer if normalizer else lambda x:x
        if isinstance(dim, int):
            self._dim = (None,) * dim
        elif isinstance(dim, tuple):
            self._dim = dim
        else:
            raise TypeError('dim parameter must be integer or tuple of integer')
        self._doc = doc

    def __call__(self, name, val):
        if not self._dim:
            self._check(name, val)
        else:
            def breakdown(dim, val):
                n = dim[0]
                if n is None:
                    n = len(val)
                if (len(dim) == 1):
                    for i in xrange(n):
                        self._check(name, val[i])
                else:
                    dim = dim[1:]
                    for i in xrange(n):
                        breakdown(dim, val[i])
            breakdown(self._dim, val)

    def _check(self, name, val):
        val = self._normalizer(val)

        if val in self._accepts:
            return
        if self._accepts_only:
            raise TypeError('Parameter %s must be one of %s' % (name, self._accepts))

        if self._types:
            if not isinstance(val, self._types):
                raise TypeError('Parameter %s require %s, but assigned value %s is not.' %
                                (name, self._types, val))
        if self._min is not None:
            if val < self._min:
                raise TypeError('Assigned value %s for parameter %s is too small.' % (val, name))

        if self._inf is not None:
            if val <= self._inf:
                raise TypeError('Assigned value %s for parameter %s is too small.' % (val, name))

        if self._max is not None:
            if val > self._max:
                raise TypeError('Assigned value %s for parameter %s is too big.' % (val, name))

        if self._sup is not None:
            if val >= self._sup:
                raise TypeError('Assigned value %s for parameter %s is too big.' % (val, name))

        if self._pred is not None:
            self._pred(name, val)

class _ArgChecker(object):
    def __init__(self, **keywords):
        self._check_all = None
        self._db = {}
        for key, chk in keywords.items():
            if key == '_':
                if not callable(chk):
                    raise TypeError('Parameter of %s must be callable.' % key)
                self._check_all = chk
            else:
                if not isinstance(chk, Check):
                    raise TypeError('Parameter of %s must be Check object.' % key)
                self._db[key] = chk

    def __call__(self, argdic):
        for key, val in argdic.iteritems():
            if key in self._db:
                self._db[key](key, val)
        if self._check_all:
            self._check_all(argdic)

def parameter(**kws):
    def wrapper(f):
        if VALIDATION_DISABLE:
            return f
        ac = _ArgChecker(**kws)
        return prehook_wrapper(f, ac, as_dict=True)
    return wrapper

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []
