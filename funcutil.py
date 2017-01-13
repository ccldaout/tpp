# -*- coding: utf-8 -*-

import inspect
import functools

#----------------------------------------------------------------------------
#                             wrapper generator
#----------------------------------------------------------------------------

def get_sig(aspec):
    if aspec.defaults:
        dc = len(aspec.defaults)
        for a in aspec.args[:-dc]:
            yield a
        for a, d in zip(aspec.args[-dc:], aspec.defaults):
            yield '%s=%s' % (a, repr(d))
    else:
        for a in aspec.args:
            yield a
    if aspec.varargs:
        yield '*' + aspec.varargs
    if aspec.keywords:
        yield '**' + aspec.keywords

def get_kws(aspec):
    for a in aspec.args:
        yield '%s=%s' % (a, a)
    if aspec.varargs:
        yield '*' + aspec.varargs
    if aspec.keywords:
        yield '**' + aspec.keywords

def get_vns(aspec):
    for a in aspec.args:
        yield a
    if aspec.varargs:
        yield aspec.varargs
    if aspec.keywords:
        yield aspec.keywords

def prehook_wrapper(f, prehook):
    aspec = inspect.getargspec(f)

    f_name = f.__name__
    f_sig = ', '.join(get_sig(aspec))    
    f_kws = ', '.join(get_kws(aspec))     

    vns = set(get_vns(aspec))
    pre_name = 'prehook'
    for _ in xrange(len(''.join(vns))):
        if pre_name not in vns:
            break
        pre_name += '_'

    m_name = 'maker'
    src = '''def %s(%s, %s):
    def _%s(%s):
        %s(%s)
        return %s(%s)
    return _%s''' % (
    m_name, f_name, pre_name,
    f_name, f_sig,
    pre_name, f_kws,
    f_name, f_kws,
    f_name)

    dic = {}
    eval(compile(src, f.__module__, 'exec'), dic)
    _f = functools.wraps(f)(dic[m_name](f, prehook))
    return _f

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []
