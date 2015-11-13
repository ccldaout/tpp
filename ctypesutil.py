# -*- coding: utf-8 -*-

from tpp.ctypessyms import *

##############################################################################
#                            extension of ctypes
##############################################################################

# addtional methods

def dump(self, printer=None):
    def _isallzero(cdata, csize=0):
        if isinstance(cdata, int):
            return (cdata == 0)
        elif isinstance(cdata, float):
            return (cdata == 0.0)
        elif isinstance(cdata, basestring):
            return (len(cdata) == 0)
        if csize == 0:
            csize = c_sizeof(cdata)
        return (c_string_at(c_addressof(cdata), csize).count('\x00') == csize)

    def _dump(ind, name, obj, printer):
        if name[:2] == '__':
            return
        if hasattr(obj, '_fields_'):
            printer('%*s%s {', ind, ' ', name)
            for m in obj._fields_:
                _dump(ind+2, m[0], getattr(obj, m[0]), printer)
            printer('%*s}', ind, ' ')
        elif isinstance(obj, str):
            printer('%*s%s: <%s>', ind, ' ', name, obj)
        elif hasattr(obj, '__len__'):
            for i in xrange(len(obj)):
                if i == 0 or not _isallzero(obj[i]):
                    idxm = '%s[%3d]' % (name, i)
                    _dump(ind, idxm, obj[i], printer)
        else:
            printer('%*s%s: %s', ind, ' ', name, str(obj))

    def _print(fmt, *args):
        print fmt % args

    if not printer:
        printer = _print
    _dump(2, '_', self, printer)

def copy(self, trg=None):
    if trg:
        c_memmove(c_addressof(trg), c_addressof(self), c_sizeof(self))
    else:
        trg = type(self).from_buffer_copy(self)
    return trg

def clear(self):
    c_memset(c_addressof(self), 0, c_sizeof(self))

# Suppress TypeError when assigninig a float value to int type.

def _wrap_setattr(setattr_):
    def _setattr(self, mbr, val):
        if isinstance(val, float):
            try:
                setattr_(self, mbr, val)
            except TypeError:
                setattr_(self, mbr, int(val))
        else:
            setattr_(self, mbr, val)
    return _setattr

def _wrap_setitem(setitem_):
    def _setitem(self, idx, val):
        setitem_(self, idx, int(val))
    return _setitem

# Enable a ctypes array to be cPickled.

_c_array = (c_int*2).__bases__[0]

def is_array(ctype):
    return issubclass(ctype, _c_array)

def _ctypes_analyze(ctype):
    cdata = ctypes.Structure.__base__
    ds = []
    if not issubclass(ctype, cdata):
        return None
    while hasattr(ctype, '_length_'):
        ds.append(getattr(ctype, '_length_'))
        ctype = getattr(ctype, '_type_')
    return (ctype, ds)

def _array_unpickle((ctype, ds), bs):
    for n in reversed(ds):
        ctype *= n
    return array(ctype).from_buffer(bs)

def _array_reduce(self):
    return (_array_unpickle,
            (_ctypes_analyze(type(self)),
             bytearray(c_string_at(c_addressof(self), c_sizeof(self)))),
            )

def array(ctype):
    orgctype = ctype
    while hasattr(ctype, '_length_'):
        ctype.__reduce__ = _array_reduce
        ctype.copy = copy
        ctype.clear = clear
        ctype.dump = dump
        ctype2 = ctype
        ctype = ctype._type_
    if issubclass(ctype, (c_int, c_long, c_uint, c_ulong)):
        ctype2.__setitem__ = _wrap_setitem(ctype2.__setitem__)
    return orgctype

# Custom Structure and Union classes.

def _setup_array(dic):
    if '_fields_' in dic:
        for fld in dic['_fields_']:
            if is_array(fld[1]):
                array(fld[1])

class _MetaStruct(type(ctypes.Structure)):
    def __new__(mcls, name, bases, dic):
        _setup_array(dic)
        return super(_MetaStruct, mcls).__new__(mcls, name, bases, dic)

    def __mul__(cls, val):
        newcls = super(_MetaStruct, cls).__mul__(val)
        return array(newcls)

class _MetaUnion(type(ctypes.Union)):
    def __new__(mcls, name, bases, dic):
        _setup_array(dic)
        return super(_MetaUnion, mcls).__new__(mcls, name, bases, dic)

    def __mul__(cls, val):
        newcls = super(_MetaUnion, cls).__mul__(val)
        return array(newcls)

class Struct(ctypes.Structure):
    __metaclass__ = _MetaStruct
    copy = copy
    clear = clear
    dump = dump
    __setattr__ = _wrap_setattr(ctypes.Structure.__setattr__)
    def __iter__(self):
        return iter((getattr(self, mbr[0]) for mbr in self._fields_))

class Union(ctypes.Union):
    __metaclass__ = _MetaUnion
    copy = copy
    clear = clear
    dump = dump
    __setattr__ = _wrap_setattr(ctypes.Union.__setattr__)
    # Union need no __iter__.

__all__ = []

##############################################################################
#                                 TEST code
##############################################################################

if __name__ == '__main__':
    import cPickle as cp
    class Test(Struct):
        _fields_ = [('name', c_char*16), ('nums', c_int*4*5*6)]
    print type(Test().name)
    print _ctypes_analyze(type(Test().name))
    print _ctypes_analyze(type(Test().nums))
    t = Test()
    t.nums[0][0][0] = 111
    t.nums[5][4][3] = 543.12
    cp.dumps(t.nums)
    cp.loads(cp.dumps(t.nums))
    t2 = cp.loads(cp.dumps(t.nums))
    print t2[0][0][0]
    print t2[5][4][3]
    reduce = _array_reduce
    (Test*2)().dump()
    pass
