# -*- coding: utf-8 -*-

import inspect
import functools

#----------------------------------------------------------------------------
#                       string operation of arguments
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

#----------------------------------------------------------------------------
#                             symbol management
#----------------------------------------------------------------------------

class Symbols(object):
    def __init__(self, names):
        self._names = set(names)

    def uniq(self, prefix):
        while True:
            if prefix not in self._names:
                self._names.add(prefix)
                return prefix
            prefix += '_'

#----------------------------------------------------------------------------
#                             wrapper generator
#----------------------------------------------------------------------------

def prehook_wrapper(f, prehook, as_dict=False):
    arg = Arguments(f)
    syms = Symbols(arg.varnames)

    m_name = 'maker'
    f_name = syms.uniq(f.__name__)
    g_name = syms.uniq('_' + f.__name__)
    pre_name = syms.uniq('prehook')
    d_name = syms.uniq('_ndict')
    f_sig = arg.as_sig
    f_kws = arg.as_kws
    if as_dict:
        d_imp = '\n    from tpp.toolbox import nameddict as %s' % d_name
        p_arg = '%s({%s})' % (d_name, arg.as_dic)
    else:
        d_imp = ''
        p_arg = f_kws

    src = '''def %s(%s, %s):%s
    def %s(%s):
        %s(%s)
        return %s(%s)
    return %s''' % (
        m_name, f_name, pre_name,
        d_imp,
        g_name, f_sig,
        pre_name, p_arg,
        f_name, f_kws,
        g_name)
    print src

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
