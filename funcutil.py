# -*- coding: utf-8 -*-

import inspect
import functools

#----------------------------------------------------------------------------
#                             wrapper generator
#----------------------------------------------------------------------------

class Arguments(object):
    def __init__(self, f):
        self._args, self._varargs, self._keywords, self._defaults = inspect.getargspec(f)

    @property
    def as_sig(self):
        def _sig():
            if self._defaults:
                dc = len(self._defaults)
                for a in self._args[:-dc]:
                    yield a
                for a, d in zip(self._args[-dc:], self._defaults):
                    yield '%s=%s' % (a, repr(d))
            else:
                for a in self._args:
                    yield a
            if self._varargs:
                yield '*' + self._varargs
            if self._keywords:
                yield '**' + self._keywords
        return ', '.join(_sig())    

    @property
    def as_kws(self):
        def _kws():
            args=list(self._args)
            for a in args:
                yield '%s=%s' % (a, a)
            if self._varargs:
                yield '*' + self._varargs
            if self._keywords:
                yield '**' + self._keywords
        return ', '.join(_kws())    

    @property
    def as_dic(self):
        def _dic():
            args=list(self._args)
            if self._varargs:
                args.append(self._varargs)
            if self._keywords:
                args.append(self._keywords)
            for a in args:
                yield '"%s":%s' % (a, a)
        return ', '.join(_dic())

    @property
    def varnames(self):
        for a in self._args:
            yield a
        if self._varargs:
            yield self._varargs
        if self._keywords:
            yield self._keywords

def prehook_wrapper(f, prehook, as_dict=False):
    arg = Arguments(f)

    f_sig = arg.as_sig
    f_kws = arg.as_kws
    if as_dict:
        p_arg = '{%s}' % arg.as_dic
    else:
        p_arg = f_kws

    vns = set(arg.varnames)
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
    pre_name, p_arg,
    f_name, f_kws,
    f_name)

    dic = {}
    eval(compile(src, f.__module__, 'exec'), dic)
    _f = functools.wraps(f)(dic[m_name](f, prehook))
    return _f

def prehook(hook, as_dict=False):
    '''decorator of prehook_wrapper'''
    def _prehook(f):
        return prehook_wrapper(f, hook, as_dict)
    return _prehook

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []
