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

def get_kws(aspec, rename_self=False):
    args=list(aspec.args)
    if rename_self and args and args[0] == 'self':
        yield 'self_original=%s' % args[0]
        args.pop(0)
    for a in args:
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

    f_sig = ', '.join(get_sig(aspec))    
    f_kws = ', '.join(get_kws(aspec))     
    f_kws2 = ', '.join(get_kws(aspec, rename_self=True))

    vns = set(get_vns(aspec))
    pre_name = 'prehook'
    for _ in xrange(len(''.join(vns))):
        if pre_name not in vns:
            break
        pre_name += '_'

    f_name = f.__name__
    for _ in xrange(len(''.join(vns))):
        if f_name not in vns:
            break
        f_name += '_'

    m_name = 'maker'
    src = '''def %s(%s, %s):
    def _%s(%s):
        %s(%s)
        return %s(%s)
    return _%s''' % (
    m_name, f_name, pre_name,
    f_name, f_sig,
    pre_name, f_kws2,
    f_name, f_kws,
    f_name)

    dic = {}
    eval(compile(src, f.__module__, 'exec'), dic)
    _f = functools.wraps(f)(dic[m_name](f, prehook))
    return _f

def prehook(hook):
    '''decorator of prehook_wrapper'''
    def _prehook(f):
        return prehook_wrapper(f, hook)
    return _prehook

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []
