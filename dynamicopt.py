# -*- coding: utf-8 -*-

# [ REMARK ]
#
#   tpp.ctypesutil depend on tpp.toolbox and tpp.toolbox depend on this
#   tpp.dynamicopt. This dependencies means that this module can NOT use
#   funcions of tpp.cytypeutil. As a result, this module use ORIGINAL CTYPES
#   instread of tpp.ctypesutil.

# [CASE1] call `option` with FILE argument
#
#   # For application which know FILE to be mapped.
#
#   from tpp.dynamicopt import option
#   with option(FILE) as define:
#       define(KEY, TYPE, COMMENT[, INITIAL_VALUE)
#	                :
# [CASE2] call `option` with no argument
#
#   # For library module which can't know FILE to be mapped.
#   #
#   # (1) if opt has not been called with FILE parameter, opt still use 
#   #     private memory.
#   # (2) if opt has been called with FILE parameter previously, opt
#   #     remember FILE and map it again in next with statement.
#   
#   from tpp.dynamicopt import option
#   with option as define:
#       define(KEY, TYPE, COMMENT[, INITIAL_VALUE)
#	                :

import ctypes
import fcntl
import mmap
import os

def ___(func, ret_if_exc=None):
    def _f(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            return ret_if_exc
    return _f

class Option(object):

    __slots__ = ('_Option__attr', '_Option__cache', '_Option__reserve',
                 '_Option__name', '_Option__user',
                 '_Option__mobj', '_Option__cobj', '_Option__fobj')

    __MAPSIZE_b = 8192
    __MAGIC = '$OPT'
    __IDXLIM = 255		# 255 is deduced by type of idxcnt (uint_8)

    class _union(ctypes.Union):
        _fields_ = [('i', ctypes.c_int64),
                    ('u', ctypes.c_uint64),
                    ('f', ctypes.c_double)]
        def __setattr__(self, attr, val):
            if attr in ('i', 'u') and isinstance(val, float):
                val = int(val)
            super(Option._union, self).__setattr__(attr, val)

    def __new__(cls):
        self = super(Option, cls).__new__(cls)
        self.__attr = []	# list of (ident, type_s, comment)
        self.__cache = {}	# depend on __attr except comment (__attr[*][2])
        self.__reserve = {}
        self.__name = None
        self.__user = None
        self.__fobj = None	# opened file object
        self.__mobj = None
        self.__cobj = self.__make_cobj()
        return self

    # ---- utilities methods -----

    def __check_ident(self, ident, dupcheck=False):
        if not ident.replace('_', '').isalnum():
            raise KeyError("Identifier '%s' has an invalid character" % ident)
        if ident[0] == '_':
            raise KeyError("Identifier '%s' dont't start with '_'." % ident)
        if dupcheck:
            if self.__find_attr(ident)[0] is not None:
                raise KeyError("Identifier '%s' is already exists." % ident)

    def __check_type_s(self, type_s):
        if type_s.lower() not in ('i', 'u', 'f'):
            raise TypeError("type_s must be one of i, u, f.")

    def __check_comment(self, comment):
        if '\0' in comment or '\n' in comment or '\t' in comment:
            raise TypeError('Comment include an invalid characeter.')

    def __make_cobj(self, reqidxcnt=__IDXLIM, buffer=None):
        attrsiz = self.__MAPSIZE_b - (reqidxcnt * 8) - 8
        class _Option(ctypes.Structure):
            _fields_ = [('magic', ctypes.c_char*4),
                        ('idxcnt', ctypes.c_uint8),
                        ('idxnxt', ctypes.c_uint8),
                        ('_pad', ctypes.c_uint8*2),
                        ('v', self._union*reqidxcnt),
                        ('attr_s', ctypes.c_char*attrsiz)]
            def dup(self):
                return type(self).from_buffer_copy(self)
            def clear(self):
                ctypes.memset(ctypes.addressof(self), 0, ctypes.sizeof(self))
                pass
        if buffer:
            return _Option.from_buffer(buffer)
        else:
            co = _Option()
            co.magic = self.__MAGIC
            co.idxcnt = reqidxcnt
            return co

    def __make_attr(self, cobj):
        def g():
            for i, attr in enumerate(cobj.attr_s.split('\n')):
                if i == cobj.idxcnt:
                    return
                a = attr.split('\t')
                if len(a) == 3:
                    if not a[1]:
                        a[1] = 'i'
                    yield a
        return list(g())

    def __remake_py_attr(self):
        self.__attr = self.__make_attr(self.__cobj)
        self.__cache = {}
        assert self.__cobj.idxnxt == len(self.__attr)

    def __remake_cobj_attr_s(self):
        self.__cobj.attr_s = '\n'.join(('%s\t%s\t%s' % (i, t, c)
                                       for i, t, c in self.__attr))

    def __find_attr(self, ident):
        for i, attr in enumerate(self.__attr):
            if attr[0] == ident:
                return i, attr
        return None, (None, None, None)

    def __get_attr(self, ident):
        idx, attr = self.__find_attr(ident)
        if idx is None:
            raise KeyError("Idenfier '%s' is not found." % ident)
        return idx, attr

    def __open_excl(self, create_if):
        if '/' not in self.__name:
            path = os.path.expanduser('~%s/.tpp/dynamicopt' % self.__user)
            ___(os.makedirs)(path, 0755)
            path = os.path.join(path, self.__name)
        else:
            path = self.__name
        o_flags = os.O_RDWR
        if create_if:
            o_flags |= os.O_CREAT
        fd = os.open(path, o_flags, 0666)
        if os.geteuid() == 0 and '/' not in self.__name and self.__user != '':
            optdir = os.path.dirname(path)
            tppdir = os.path.dirname(optdir)
            st = os.stat(os.path.dirname(tppdir))	# ~<user>
            os.chown(tppdir, st.st_uid, st.st_gid)
            os.chown(optdir, st.st_uid, st.st_gid)
            os.chown(path, st.st_uid, st.st_gid)
        ___(os.chmod)(path, 0666)		# os.fchmod is not exist in Pythonista
        fcntl.lockf(fd, fcntl.LOCK_EX)		# Exclusive lock until file is closed.
        return os.fdopen(fd, 'r+b')

    def __mmap(self):
        self.__fobj.truncate(self.__MAPSIZE_b)
        mo = mmap.mmap(self.__fobj.fileno(), 0, access=mmap.ACCESS_WRITE)
        co = self.__make_cobj(1, mo)
        if co.magic != self.__MAGIC:
            co.clear()
            co.magic = self.__MAGIC
            co.idxcnt = self.__IDXLIM
            co.idxnxt = 0
        co = self.__make_cobj(co.idxcnt, mo)

        dupids = (set([a[0] for a in self.__make_attr(co)]) &
                  set([a[0] for a in self.__attr]))
        if dupids:
            for ident in dupids:
                self._remove(ident)		# Performance problem !!
        if self.__cobj.idxnxt + co.idxnxt > co.idxcnt:
            raise TypeError('Index table overflow.')
        if self.__cobj.idxnxt:
            n = self.__cobj.idxnxt
            co.v[co.idxnxt:co.idxnxt+n] = self.__cobj.v[:n]
            co.attr_s = co.attr_s + '\n' + self.__cobj.attr_s
            co.idxnxt += self.__cobj.idxnxt

        self.__mobj = mo
        self.__cobj = co
        self.__remake_py_attr()

    def __unmap(self):
        if self.__mobj:
            self.__cobj = self.__cobj.dup()
            self.__mobj.close()
            self.__mobj = None
            self.__remake_py_attr()

    # ---- Fundamental methods -----

    def __define(self, ident, type_s, comment, val=None):
        _, (i, t, c) = self.__find_attr(ident)
        if (i, t, c) == (ident, type_s, comment):
            return		# same definition except inital value is allowed.

        self.__check_ident(ident, dupcheck=True)
        self.__check_type_s(type_s)
        self.__check_comment(comment)
        if self.__cobj.idxnxt == self.__cobj.idxcnt:
            raise Exception('Too many definitions.')

        self.__attr.append((ident, type_s.lower(), comment))
        self.__cobj.idxnxt += 1
        self.__remake_cobj_attr_s()
        if ident in self.__reserve:
            setattr(self, ident, self.__reserve.pop(ident))
        elif val and self.__cobj.v[self.__cobj.idxnxt-1].i == 0:
            setattr(self, ident, val)

        assert self.__cobj.idxnxt == len(self.__attr)

    def __enter__(self):
        self.__unmap()
        if self.__name:
            try:
                self.__fobj = self.__open_excl(True)
                self.__mmap()
            except:
                pass
        return self.__define

    def __exit__(self, exc_type, exc_value, exc_traceback):
        # - __fobj.close() release lock acquired in __open_excl.
        # - Don't call __umap because changing by outside can't effect.
        if self.__fobj:
            self.__fobj.close()
            self.__fobj = None

    def __call__(self, name='', user=''):
        self.__name = name
        self.__user = user
        return self

    def __getattr__(self, attr):
        uobj, type_s = self.__cache.get(attr, (None, None))
        if uobj is None:
            idx, (_, type_s, _) = self.__find_attr(attr)
            if idx is None:
                return 0
            uobj = self.__cobj.v[idx]
            self.__cache[attr] = (uobj, type_s)
        return getattr(uobj, type_s)

    def __setattr__(self, attr, val):
        if attr in self.__slots__:
            super(Option, self).__setattr__(attr, val)
        else:
            self.__check_ident(attr, dupcheck=False)
            idx, (ident, type_s, _) = self.__find_attr(attr)
            if idx is None:
                self.__reserve[attr] = val
            else:
                return setattr(self.__cobj.v[idx], type_s, val)

    def _load(self):
        self.__unmap()
        if self.__name:
            with self.__open_excl(False) as f:
                self.__fobj = f
                self.__mmap()
                self.__fobj.close()

    def _show(self):
        sorted_attr = sorted(enumerate(self.__attr), key=lambda v:v[1][0])
        for i, (idx, (ident, type_s, comment)) in enumerate(sorted_attr):
            if ident:
                v = getattr(self.__cobj.v[idx], type_s)
                print '%3d: %20s:%s %8s | %s' % (
                    i, ident, type_s, v, comment)

    # ---- Additional management methods -----

    def _reset(self):
        self.__unmap()
        self.__attr = []
        self.__cache = {}
        self.__cobj.clear()
        self.__cobj.magic = self.__MAGIC
        self.__cobj.idxcnt = self.__IDXLIM
        self.__cobj.idxnxt = 0
        self.__remake_cobj_attr_s()

    def _rename(self, ident, newident):
        idx, (_, t, c) = self.__get_attr(ident)
        self.__check_ident(newident, dupcheck=True)
        self.__attr[idx] = (newident, t, c)
        self.__remake_cobj_attr_s()
        if ident in self.__cache:
            self.__cache[newident] = self.__cache[ident]

    def _chtype(self, ident, newtype_s):
        idx, (_, _, c) = self.__get_attr(ident)
        self.__check_type_s(newtype_s)
        v = getattr(self, ident)
        self.__attr[idx] = (ident, newtype_s.lower(), c)
        self.__cache = {}
        setattr(self, ident, v)
        self.__remake_cobj_attr_s()

    def _chcomment(self, ident, newcomment):
        idx, (_, t, _) = self.__get_attr(ident)
        self.__check_comment(newcomment)
        self.__attr[idx] = (ident, t, newcomment)
        self.__remake_cobj_attr_s()

    def _remove(self, ident):
        idx, _ = self.__get_attr(ident)
        del self.__attr[idx]
        self.__cache = {}
        end = self.__cobj.idxnxt
        self.__cobj.v[idx:end-1] = self.__cobj.v[idx+1:end]
        self.__cobj.v[end-1].i = 0
        self.__cobj.idxnxt -= 1
        self.__remake_cobj_attr_s()

    # ---- Convenience methods -----

    def __iter__(self):
        return iter(self.__attr)

    def __len__(self):
        return len(self.__attr)

    def __contains__(self, ident):
        idx, (ident, type_s, _) = self.__find_attr(ident)
        return idx is not None

option = Option()
with option('tpp.default'):
    pass

__all__ = ['option']

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        if not sys.flags.interactive:
            prms = (os.path.basename(sys.argv[0]).rstrip('.py'),
                    sys.argv[1] if len(sys.argv) == 2 else 'OPTMAP')
            print 'Usage: python -m %s %s show' % prms
            print '     : python -m %s %s ident[=value] [ident[=value] ...]' % prms
    elif sys.argv[2] == 'show':
        option(sys.argv[1])._load()
        option._show()
    else:
        option(sys.argv[1])._load()
        for expr in sys.argv[2:]:
            subexprs = expr.split('=')
            if len(subexprs) == 1:
                ident = subexprs[0]
                print '%s=%s' % (ident, getattr(option, ident))
            elif len(subexprs) != 2:
                raise TypeError('Invalid assignment expression: %s' % expr)
            else:
                ident, value = subexprs
                try:
                    value = int(value, base=0)
                except:
                    value = float(value)
                setattr(option, ident, value)
    os._exit(0)
