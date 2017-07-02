# -*- coding: utf-8 -*-

# [CASE1] call parameter with FILE and CTYPES_CLASS argument
#
#   # for application which know CTYPES_CLASS
#
#   from tpp.dynamicprm import parameter
#   parameter(FILE, ctypes_class)
#
# [CASE2] call parameter without CTYPES_CLASS argument
#
#   # for outside of application
#
#   from tpp.dynamicprm import parameter
#   with parameter(FILE) as cmd:
#     cmd.show()

import cPickle
import mmap
import os
from tpp import ctypesutil as cu
from tpp.ctypessyms import *
from tpp.funcutil import Symbols
from tpp.toolbox import alignP2, no_except as ___


class PortableCtype(object):
    
    __slots__ = ('_name', '_c_class', '_fields')

    _PRIMITIVES = set([c_void_p, c_char_p,
                       c_char, c_short, c_int, c_long,
                       c_ushort, c_uint, c_ulong,
                       c_int8, c_int16, c_int32, c_int64,
                       c_uint8, c_uint16, c_uint32, c_uint64,
                       c_float, c_double,
                       c_size_t])

    _symbols = Symbols([])
    _convtab = {}	# original_c_type -> protable_type
    _gendict = {}	# portable_type -> restored_c_type

    def __init__(self, ctype):
        self._name = self._symbols.uniq(ctype.__name__)
        self._convtab[ctype] = self

        if issubclass(ctype, cu.Struct):
            self._c_class = cu.Struct
        elif issubclass(ctype, cu.Union):
            self._c_class = cu.Union
        else:
            raise TypeError('PortableCtype accpet only structure or union.')

        def scan():
            for fld in ctype._fields_:
                fld = list(fld)
                if cu.is_array(fld[1]):
                    t, ds = cu.analyze_ctypes(fld[1])
                else:
                    t, ds = fld[1], ()
                if t not in self._PRIMITIVES:
                    if t not in self._convtab:
                        t = PortableCtype(t)
                    else:
                        t = self._convtab[t]
                fld[1] = (t, ds)
                yield fld
        self._fields = list(scan())

    @classmethod
    def reset(cls):
        cls._symbols = Symbols([])
        cls._convtab = {}
        cls._gendict = {}

    def __repr__(self):
        return self._name

    def _show(self, cache):
        for fld in self._fields:
            t, ds = fld[1]
            if t not in self._PRIMITIVES and t not in cache:
                cache.add(t)
                t._show(cache)
        print '%s(%s):' % (self._name, self._c_class.__name__)
        for fld in self._fields:
            print '    %s : %s %s' % (fld[0], fld[1],
                                      fld[2] if len(fld) == 3 else '')
        print

    def show(self):
        self._show(set())

    def dumps(self):
        return cPickle.dumps(self, 2)

    @staticmethod
    def loads(s):
        return cPickle.loads(s)

    def dump(self, path):
        with open(path, 'w') as f:
            cPickle.dump(self, f, 2)

    @staticmethod
    def load(path):
        with open(path) as f:
            return cPickle.load(f)

    def gen_class(self):
        for fld in self._fields:
            t, ds = fld[1]
            if t not in self._PRIMITIVES and t not in self._gendict:
                t.gen_class()
        def gen_fields():
            for fld in self._fields:
                fld = list(fld)
                t, ds = fld[1]
                if isinstance(t, type(self)):
                    t = self._gendict[t]
                if ds:
                    for n in reversed(ds):
                        t *= n
                fld[1] = t
                yield tuple(fld)
        fields = list(gen_fields())
        cls = type(self._name, (self._c_class,), {'_fields_':fields})
        self._gendict[self] = cls
        return cls

class Parameter(object):

    __slots__ = ('_Parameter__mobj', '_Parameter__cobj')

    __MAX_PICKLED_CTYPE = 1024*64
    __MAGIC = '$COP'

    def __new__(cls):
        self = super(Parameter, cls).__new__(cls)
        self.__mobj = None
        self.__cobj = None
        return self

    @staticmethod
    def __pickle(o_type):
        return PortableCtype(o_type).dumps()

    @staticmethod
    def __unpickle(pickled_type):
        return PortableCtype.loads(pickled_type).gen_class()

    def __cobj_class(self, o_type, pickled_size):
        pickled_size = alignP2(pickled_size + 1, 8)
        class _prmmap_t(cu.Struct):
            _fields_ = [('magic', cu.c_char*4),
                        ('pickled_size', cu.c_int32),
                        ('_pad', cu.c_int32*2),
                        # c_char[] is not suitable for pickled data which may include
                        # null byte inside.
                        ('PICKLED_TYPE_b', cu.c_uint8*pickled_size),
                        ('prm', o_type)]
        return _prmmap_t

    def __open(self, name):
        if '/' not in name:
            path = os.path.expanduser('~/.tpp/dynamicprm')
            ___(os.makedirs)(path)
            path = os.path.join(path, name)
        else:
            path = name
        fd = os.open(path, os.O_RDWR|os.O_CREAT, 0666)
        return os.fdopen(fd, 'r+b')

    @staticmethod
    def __co_pickled_type(co, save_pickled_type=None):
        if save_pickled_type:
            co.pickled_size = len(save_pickled_type)
            for i, b in enumerate(bytearray(save_pickled_type)):
                co.PICKLED_TYPE_b[i] = b
        else:
            return str(bytearray((co.PICKLED_TYPE_b[i]
                                  for i in xrange(co.pickled_size))))

    def __extract(self, f):
        mobj = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        t = self.__cobj_class(cu.c_int32, 4)
        co = t.from_buffer_copy(mobj)
        if co.magic != self.__MAGIC or co.pickled_size > self.__MAX_PICKLED_CTYPE:
            raise Exception('Invalid file format.')

        t = self.__cobj_class(cu.c_int32, co.pickled_size)
        co = t.from_buffer_copy(mobj)
        pickled_type = self.__co_pickled_type(co)
        o_type = self.__unpickle(pickled_type)

        mobj.close()
        return o_type, pickled_type

    def __call__(self, name, o_type=None):
        if o_type:
            pickled_type = self.__pickle(o_type)
            if len(pickled_type) > self.__MAX_PICKLED_CTYPE:
                raise Exception('Passed o_type is too big to be pickled.')

        with self.__open(name) as f:
            if o_type is None:
                o_type, pickled_type = self.__extract(f)
            c_type = self.__cobj_class(o_type, len(pickled_type))
            f.truncate(cu.c_sizeof(c_type))
            if self.__mobj:
                self.__mobj.close()
            self.__mobj = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_WRITE)
            self.__cobj = co = c_type.from_buffer(self.__mobj)

        if (co.magic != self.__MAGIC or self.__co_pickled_type(co) != pickled_type):
            co.clear()
            co.magic = self.__MAGIC
            self.__co_pickled_type(co, pickled_type)

        return self

    def __enter__(self):
        class Operator(object):
            pass
        o = Operator()
        o.show = self.__show
        return o

    def __exit__(self, exc_type, exc_value, exc_traceback):
        pass

    def __getattr__(self, attr):
        return getattr(self.__cobj.prm, attr)

    def __setattr__(self, attr, v):
        if attr in self.__slots__:
            return super(Parameter, self).__setattr__(attr, v)
        return setattr(self.__cobj.prm, attr, v)

    def __show(self):
        self.__cobj.prm.dump()

parameter = Parameter()

__all__ = ['parameter']

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        if not sys.flags.interactive:
            prms = (os.path.basename(sys.argv[0]).rstrip('.py'),
                    sys.argv[1] if len(sys.argv) == 2 else 'PRMMAP')
            print 'Usage: python -m %s %s show' % prms
            print '     : python -m %s %s member[.member...][=value] ...' % prms
    elif sys.argv[2] == 'show':
        with parameter(sys.argv[1]) as cmd:
            cmd.show()
    else:
        with parameter(sys.argv[1]): pass
        def lastref(ident):
            ids = ident.split('.')
            obj = parameter
            for mbr in ids[:-1]:
                obj = getattr(obj, mbr)
            return obj, ids[-1]
        for expr in sys.argv[2:]:
            subexprs = expr.split('=')
            if len(subexprs) == 1:
                obj, ident = lastref(subexprs[0])
                print getattr(obj, ident)
            elif len(subexprs) != 2:
                raise TypeError('Invalid assignment expression: %s' % expr)
            else:
                ident, value = subexprs
                obj, ident = lastref(ident)
                try:
                    setattr(obj, ident, value)
                except TypeError:
                    try:
                        value = int(value, base=0)
                    except:
                        try:
                            value = float(value)
                        except:
                            pass
                    setattr(obj, ident, value)
    os._exit(0)
