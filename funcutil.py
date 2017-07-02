# -*- coding: utf-8 -*-

import inspect
import functools
import os
from tpp.dynamicopt import option as _opt

with _opt as _def:
    _def('TPP_PRINT_SRC', 'i', '[tpp.funcutil] print generated source', 0)

#----------------------------------------------------------------------------
#
#----------------------------------------------------------------------------

### def gen_func(fname, src, dic=None, filename=None):
###     if filename is None:
###         filename = '<generate %s>' % fname
###     if dic is None:
###         dic = {}
###     if TPP_PRINT_SRC:
###         print src
###     eval(compile(src, filename, 'exec'), dic)
###     return dic[fname]
### 
### Next gen_func is slightly faster than above gen_func by difference of
### each lookup costs. 
###
def gen_func(fname, src, dic=None, filename=None):
    if filename is None:
        filename = '<generate %s>' % fname
    if dic is None:
        dic = {}
    if _opt.TPP_PRINT_SRC:
        print src
    mn = '__maker'
    src = '''def %s(%s):
    %s
    return %s''' % (mn, ', '.join(dic.keys()),
                    src.replace('\n', '\n    '),
                    fname)
    mndic = {}
    eval(compile(src, filename, 'exec'), mndic)
    return mndic[mn](*dic.values())

#----------------------------------------------------------------------------
#
#----------------------------------------------------------------------------

_TPP_DOC_MODIFIED = '_TPP_DOC_MODIFIED'

def insert_doc(f, doc):
    if f.__doc__:
        f.__doc__ = doc + '\n \n' + f.__doc__
    else:
        f.__doc__ = doc
    setattr(f, _TPP_DOC_MODIFIED, True)

def wrap(original_f, sig_doc=True):
    def _wrap(wrapper_f):
        wrapper_f = functools.wraps(original_f)(wrapper_f)
        if sig_doc is True and not hasattr(wrapper_f, _TPP_DOC_MODIFIED):
            insert_doc(wrapper_f, 'Arguments: ' + Arguments(original_f).as_sig)
        elif isinstance(sig_doc, basestring):
            insert_doc(wrapper_f, sig_doc)
        return wrapper_f
    return _wrap

#----------------------------------------------------------------------------
#                       string operation of arguments
#----------------------------------------------------------------------------

class Arguments(object):
    def __init__(self, f):
        self.args, self.varargs, self.keywords, self.defaults = inspect.getargspec(f)

    @property
    def mandatory_args(self):
        if self.defaults:
            return self.args[:-len(self.defaults)]
        else:
            return self.args

    @property
    def optional_args(self):
        if self.defaults:
            return zip(self.args[-len(self.defaults):], self.defaults)
        else:
            return []

    @property
    def mandatory_as_sig(self):
        return ', '.join(self.mandatory_args)

    @property
    def optional_as_sig(self):
        return ', '.join(['%s=%s' % (k, repr(v)) for k, v in self.optional_args])

    @property
    def as_sig(self):
        def _sig():
            for a in self.mandatory_args:
                yield a
            for a, d in self.optional_args:
                yield '%s=%s' % (a, repr(d))
            if self.varargs:
                yield '*' + self.varargs
            if self.keywords:
                yield '**' + self.keywords
        return ', '.join(_sig())

    @property
    def as_arg(self):
        def _arg():
            args=list(self.args)
            for a in args:
                yield a
            if self.varargs:
                yield '*' + self.varargs
            if self.keywords:
                yield '**' + self.keywords
        return ', '.join(_arg())

    @property
    def as_dic(self):
        def _dic():
            args=list(self.args)
            if self.varargs:
                args.append(self.varargs)
            if self.keywords:
                args.append(self.keywords)
            for a in args:
                yield '"%s":%s' % (a, a)
        return ', '.join(_dic())

    @property
    def varnames(self):
        for a in self.args:
            yield a
        if self.varargs:
            yield self.varargs
        if self.keywords:
            yield self.keywords

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

def prehook_wrapper(f, prehook):
    arg = Arguments(f)
    syms = Symbols(arg.varnames)

    f_name = syms.uniq(f.__name__)
    g_name = syms.uniq('_' + f.__name__)
    pre_name = syms.uniq('_prehook')
    a_name = syms.uniq('_arg')
    f_sig = arg.as_sig
    f_dic = arg.as_dic
    f_arg = arg.as_arg

    src = '''def %s(%s):
    %s(%s, {%s})
    return %s(%s)''' % (g_name, f_sig,
                        pre_name, a_name, f_dic,
                        f_name, f_arg)
    wrapper = gen_func(g_name, src, dic={f_name:f, pre_name:prehook, a_name:arg})

    return functools.wraps(f)(wrapper)

def prehook(hook):
    '''decorator of prehook_wrapper'''
    def _prehook(f):
        return prehook_wrapper(f, hook)
    return _prehook

class Hooks(object):
    def pre(self, argdef, argdic):
        pass

    def post(self, retval):
        return retval

    def __call__(self, f, argdef, argdic):
        self.pre(argdef, argdic)
        if argdef.varargs:
            vas = argdic.pop(argdef.varargs, ())
        else:
            vas = ()
        if argdef.keywords:
            kws = argdic.pop(argdef.keywords, {})
        else:
            kws = {}
        args = [argdic[a] for a in argdef.args]
        args.extend(vas)
        return self.post(f(*args, **kws))

def hooks_wrapper(f, hooks):
    if not isinstance(hooks, Hooks):
        raise TypeError('hooks must be instance of Hooks or subclass of it.')

    arg = Arguments(f)
    syms = Symbols(arg.varnames)

    f_name = syms.uniq(f.__name__)
    g_name = syms.uniq('_' + f.__name__)
    h_name = syms.uniq('_hooks')
    a_name = syms.uniq('_arg')
    f_sig = arg.as_sig
    h_arg = '{%s}' % arg.as_dic

    src = '''def %s(%s):
    return %s(%s, %s, %s)''' % (g_name, f_sig,
                                h_name, f_name, a_name, h_arg)
    wrapper = gen_func(g_name, src, dic={f_name:f, h_name:hooks, a_name:arg})

    return functools.wraps(f)(wrapper)

def hooks(hooks):
    '''decorator of hooks_wrapper'''
    def _hooks(f):
        return hooks_wrapper(f, hooks)
    return _hooks

#----------------------------------------------------------------------------
#                             overload function
#----------------------------------------------------------------------------

class _Candidate(object):

    def __init__(self, f, types):
        self._f = f
        self._types = types
        self._count = len(types)

    def score(self, ins, own, args, kws):
        if ins is None and own is not None:
            args = args[1:]
        if self._count > len(args):
            return 0
        for t, v in zip(self._types, args):
            if not isinstance(v, t):
                return 0
        return self._count

    def call(self, ins, own, args, kws):
        if own is None:
            return self._f(*args, **kws)
        return self._f.__get__(ins, own)(*args, **kws)

class _OverloadFunction(object):

    def __new__(cls):
        self = super(_OverloadFunction, cls).__new__(cls)
        self._cands = []
        return self

    def __dispatch(self, ins, own, args, kws):
        score = 0
        match = set()
        for cand in self._cands:
            s = cand.score(ins, own, args, kws)
            if s > 0:
                if s > score:
                    score = s
                    match = set((cand,))
                elif s == score:
                    match.add(cand)
        if not match:
            raise Exception('no match')
        elif len(match) != 1:
            raise Exception('too match')
        return match.pop().call(ins, own, args, kws)

    def __get__(self, ins, own):
        def call(*args, **kws):
            return self.__dispatch(ins, own, args, kws)
        return call

    def __call__(self, *args, **kws):
        return self.__dispatch(None, None, args, kws)
    
    def overload(self, *args):
        def _overload(f):
            self._cands.append(_Candidate(f, args))
            return self
        return _overload

def overload(*args):
    return _OverloadFunction().overload(*args)

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []
