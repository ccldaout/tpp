import atexit
import gc
import os
import sys
import weakref
import __builtin__

for _m in ['warnings', 'abc'] + os.getenv('INSMON_ERR_MODULES', '').split(' '):
    if _m:
        _m = __import__(_m)
        _m.type = type
    
class _type(type):
    __original_type__ = type

    def __new__(mcls, name, bases=None, dic=None):
        if bases is None:
            return _type.__original_type__(name)
        if dic is None:
            return _type.__original_type__(name, bases)
        if ('__slots__' in dic and
            '__weakref__' not in dic['__slots__'] and
            name != '_object'):
            sl = list(dic['__slots__'])
            sl.append('__weakref__')
            dic['__slots__'] = sl
        return super(_type, mcls).__new__(mcls, name, bases, dic)
    
class _object(object):
    __metaclass__ = _type
    __slots__ = ()
    __counts__ = {}
    __gc_collect__ = gc.collect
    __objset_class__ = weakref.WeakSet

    def __new__(cls, *args, **kwargs):
        self = super(_object, cls).__new__(cls)
        try:
            s = _object.__counts__.setdefault(cls, _object.__objset_class__())
            s.add(self)
        except:
            pass
        return self

    @staticmethod
    def __show_alived__(all_=False):
        _object.__gc_collect__()
        for k, os in _object.__counts__.iteritems():
            n = len(os)
            if n or all_:
                print '%8d %s' % (len(os), k)

    @staticmethod
    def __clear_alived__():
        _object.__counts__ = {}

def enable():
    __builtin__.type = _type
    __builtin__.object = _object
    __builtin__.show_alived = _object.__show_alived__
    __builtin__.clear_alived = _object.__clear_alived__
    atexit.register(_object.__show_alived__)

__all__ = []

if __name__ == '__main__':
    enable()
    del atexit, gc, os, weakref, _m, enable
    sys.argv.pop(0)
    if sys.argv:
        _argv0 = sys.argv[0]
        del sys
        execfile(_argv0)
    else:
        del sys
