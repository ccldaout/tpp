# -*- coding: utf-8 -*-

import functools

#----------------------------------------------------------------------------
#                           Defensive programming
#----------------------------------------------------------------------------

def keywords(f):
    '''Enforce keyword parameter for optional argument'''
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
#----------------------------------------------------------------------------

__all__ = []
