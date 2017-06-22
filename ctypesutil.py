# -*- coding: utf-8 -*-

from tpp.ctypessyms import *

# additional functions

def is_array(ctype):
    return issubclass(ctype, ctypes.Array)

def analyze_ctypes(ctype):
    cdata = ctypes.Structure.__base__
    ds = []
    if not issubclass(ctype, cdata):
        return None
    while hasattr(ctype, '_length_'):
        ds.append(getattr(ctype, '_length_'))
        ctype = getattr(ctype, '_type_')
    return (ctype, ds)

# addtional methods

def dump(self, printer=None, all=False):
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
            count = 0
            limit = 0xfffffff if all else 10
            for i in xrange(len(obj)):
                if count == limit:
                    printer('%*s ... snip ...', ind, ' ')
                    break
                if i == 0 or not _isallzero(obj[i]):
                    count += 1
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

def encode(self):
    if isinstance(self, (str, int, long, float)):
        return self
    if hasattr(self, '__len__'):
        return [encode(o) for o in self]
    if hasattr(self, '_fields_'):
        return dict(((fld[0], encode(getattr(self, fld[0]))) for fld in self._fields_))
    raise Exception("%s cannot be encoded" % self)

def decode(self, eobj):
    if isinstance(eobj, list):
        if isinstance(eobj[0], (list, dict)):
            for idx, e in enumerate(eobj):
                decode(self[idx], e)
        else:
            for idx, e in enumerate(eobj):
                self[idx] = e
    elif isinstance(eobj, dict):
        for k, e in eobj.items():
            if isinstance(e, (list, dict)):
                decode(getattr(self, k), e)
            else:
                setattr(self, k, e)
    return self

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

def _array_unpickle((ctype, ds), bs):
    for n in reversed(ds):
        ctype *= n
    return array(ctype).from_buffer(bs)

def _array_reduce(self):
    return (_array_unpickle,
            (analyze_ctypes(type(self)),
             bytearray(c_string_at(c_addressof(self), c_sizeof(self)))),
            )

# Extender for ctypes array.

def array(ctype):
    def __repr__(self):
        def parts(self):
            n, ds = analyze_ctypes(type(self))
            yield n.__name__
            for d in ds:
                yield '[%d]' % d
        return ''.join(parts(self))
    orgctype = ctype
    if ctype.__reduce__ == _array_reduce:
        return orgctype
    while hasattr(ctype, '_length_'):
        ctype.__reduce__ = _array_reduce
        ctype.copy = copy
        ctype.dup = copy
        ctype.clear = clear
        ctype.dump = dump
        ctype.encode = encode
        ctype.decode = decode
        ctype.__repr__ = __repr__
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

        name = '_permit_attrs_'
        if hasattr(cls, name):
            attrs.extend(getattr(cls, name))
        setattr(cls, name, set(attrs))

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
    cls.encode = encode
    cls.decode = decode

class _MetaArray(type(ctypes.Array)):
    def __new__(mcls, name, bases, dic):
        cls = super(_MetaArray, mcls).__new__(mcls, name, bases, dic)
        return array(cls)

    def __mul__(cls, val):
        newcls = super(_MetaArray, cls).__mul__(val)
        return array(newcls)

class _MetaStruct(type(ctypes.Structure)):
    def __new__(mcls, name, bases, dic):
        cls = super(_MetaStruct, mcls).__new__(mcls, name, bases, dic)
        _setup(cls)
        return cls

    def __mul__(cls, val):
        return _MetaArray('%s_Array_%d' % (cls.__name__, val),
                          (ctypes.Array,),
                          {'_length_':val,
                           '_type_':cls})

class _MetaUnion(type(ctypes.Union)):
    def __new__(mcls, name, bases, dic):
        cls = super(_MetaUnion, mcls).__new__(mcls, name, bases, dic)
        _setup(cls)
        return cls

    def __mul__(cls, val):
        return _MetaArray('%s_Array_%d' % (cls.__name__, val),
                          (ctypes.Array,),
                          {'_length_':val,
                           '_type_':cls})

class Struct(ctypes.Structure):
    __metaclass__ = _MetaStruct

    def __iter__(self):
        return iter((getattr(self, mbr[0]) for mbr in self._fields_))

    def __repr__(self):
        def walk(co):
            hn = 4
            ct = type(co)
            yield ct.__name__ + '('
            sep = ''
            for fld in ct._fields_[:hn]:
                v = getattr(co, fld[0])
                if isinstance(v, (int, long, float, basestring)):
                    yield '%s%s:%s' % (sep, fld[0], repr(v))
                else:
                    yield '%s%s' % (sep, fld[0])
                sep = ', '
            if len(ct._fields_) > hn:
                yield ', ...'
            yield ')'
        return ''.join(walk(self))

class Union(ctypes.Union):
    __metaclass__ = _MetaUnion
    _permit_attrs_ = {'_assigned_mbr_'}

    def __setattr__(self, mbr, val):
        super(Union, self).__setattr__('_assigned_mbr_', mbr)
        return super(Union, self).__setattr__(mbr, val)

    def __repr__(self):
        mbr = self._fields_[0][0]
        if hasattr(self, '_assigned_mbr_'):
            mbr = self._assigned_mbr_
        return '%s(%s:%s)' % (type(self).__name__, mbr, repr(getattr(self, mbr)))

__all__ = []

if __name__ == '__main__':
    pass

