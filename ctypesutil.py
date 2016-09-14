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
            printer('%*s%s: <%s>', ind, ' ', name, obj.encode('string_escape'))
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
        if mbr not in self._permit_attrs_ and not self._permit_new_attr_:
            raise AttributeError('%s has no member %s.' % (type(self).__name__, mbr))
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

# Extender for ctypes array.

def array(ctype):
    orgctype = ctype
    while hasattr(ctype, '_length_'):
        ctype.__reduce__ = _array_reduce
        ctype.copy = copy
        ctype.dup = copy
        ctype.clear = clear
        ctype.dump = dump
        ctype2 = ctype
        ctype = ctype._type_
    if issubclass(ctype, (c_int, c_long, c_uint, c_ulong)):
        ctype2.__setitem__ = _wrap_setitem(ctype2.__setitem__)
    return orgctype

# Additional properties for ctypes structure object.

def _top_base(self):
    o = self
    while o._b_base_:
        o = o._b_base_
    return o

class _PropertyCacheDesc(object):
    __slots__ = ('_name',)

    class _Store(object):
        pass

    def __new__(cls, name):
        self = super(_PropertyCacheDesc, cls).__new__(cls)
        self._name = name
        return self

    def __get__(self, obj, cls):
        top = _top_base(obj)
        if self._name in top.__dict__:
            s = top.__dict__[self._name]
        else:
            s = type(self)._Store()
            top.__dict__[self._name] = s
        if top is not obj:
            obj.__dict__[self._name] = s
        return s

# Custom Structure and Union classes.

def _setup(cls):
    if hasattr(cls, '_fields_'):
        flds = cls._fields_

        attrs = [f[0] for f in flds]
        name = '_permit_new_attr_'
        if hasattr(cls, name):
            if isinstance(getattr(cls, name), (tuple, list)):
                attrs.extend(getattr(cls, name))
                setattr(cls, name, False)
        else:
            setattr(cls, name, False)
        cls._permit_attrs_ = set(attrs)

        for fld in flds:
            if is_array(fld[1]):
                array(fld[1])

    cls.__setattr__ = _wrap_setattr(cls.__setattr__)
    cls._property_ = _PropertyCacheDesc('_property_')
    cls._top_base_ = property(_top_base)
    cls.copy = copy
    cls.dup = copy
    cls.clear = clear
    cls.dump = dump

class _MetaStruct(type(ctypes.Structure)):
    def __new__(mcls, name, bases, dic):
        cls = super(_MetaStruct, mcls).__new__(mcls, name, bases, dic)
        _setup(cls)
        return cls

    def __mul__(cls, val):
        newcls = super(_MetaStruct, cls).__mul__(val)
        return array(newcls)

class _MetaUnion(type(ctypes.Union)):
    def __new__(mcls, name, bases, dic):
        cls = super(_MetaUnion, mcls).__new__(mcls, name, bases, dic)
        _setup(cls)
        return cls

    def __mul__(cls, val):
        newcls = super(_MetaUnion, cls).__mul__(val)
        return array(newcls)

class Struct(ctypes.Structure):
    __metaclass__ = _MetaStruct
    def __iter__(self):
        return iter((getattr(self, mbr[0]) for mbr in self._fields_))

class Union(ctypes.Union):
    __metaclass__ = _MetaUnion
    # Union need no __iter__.

__all__ = []

##############################################################################
#                                 TEST code
##############################################################################

if __name__ == '__main__':
    pass
