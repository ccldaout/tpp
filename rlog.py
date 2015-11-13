#!/usr/bin/python
# -*- coding: euc-jp -*-

import math
import mmap
import os
import time
import threading
import sys
from tpp.ctypessyms import *
from tpp import ctypesutil as cu
from tpp import threadutil as tu
from tpp import toolbox as tb

#----------------------------------------------------------------------------
#
#----------------------------------------------------------------------------

_HDR_REVISION = 2
_HDR_HINTSIZE = 64

class _hdr_t(cu.Struct):
    _fields_ = [ ('rev', c_uint32),
                 ('cnt', c_uint32),
                 ('hdrsize', c_uint32),
                 ('logsize', c_uint32),
                 ('nextlnkaddr', c_uint32),
                 ('hint', c_char*_HDR_HINTSIZE), ]

class _lnk_t(cu.Struct):
    _fields_ = [ ('prevlnkoff', c_uint32),
                 ('nextlnkoff', c_uint32),
                 ('tvsec', c_uint32),
                 ('tvusec', c_uint32),
                 ('snum', c_uint32),
                 ('size', c_int32), ]

class _Rbuf(object):

    def __init__(self, mmobj, offset, size):
        self._top = c_addressof((c_char*size).from_buffer(mmobj, offset))
        self._size = size
        self._end = self._top + size

    def _mcopy(self, addr, size, c_obj, read):
        rbuf = self._top + (addr % self._size)
        rrest = self._end - rbuf
        ubuf = c_addressof(c_obj)
        while size > 0:
            cpsize = size if size < rrest else rrest
            if read:
                c_memmove(ubuf, rbuf, cpsize)
            else:
                c_memmove(rbuf, ubuf, cpsize)
            ubuf += cpsize
            size -= cpsize
            rbuf = self._top
            rrest = self._size

    def get(self, addr, size, c_buf):
        self._mcopy(addr, size, c_buf, True)

    def put(self, addr, size, c_buf):
        if isinstance(c_buf, str):
            c_buf = (c_char*size).from_buffer_copy(c_buf)
        elif isinstance(c_buf, bytearray):
            c_buf = (c_char*size).from_buffer(c_buf)
        self._mcopy(addr, size, c_buf, False)

class _RlogWriter(object):

    def _setown(self, path):
        try:
            s = os.stat(os.path.dirname(path))
            os.chown(path, s.st_uid, s.st_gid)
        except:
            pass

    def _mmap(self, path):
        flags = os.O_RDWR|os.O_CREAT
        if sys.platform[:3] == 'win':
            flags |= os.O_BINARY
        self._mobj = fd = None
        try:
            fd = os.open(path, flags, 0777)
            self._setown(path)
            os.ftruncate(fd, self._mmapsize)
            self._mobj = mmap.mmap(fd, self._mmapsize)
        except:
            traceback.print_exc()
        finally:
            if fd is not None:
                os.close(fd)
        return self._mobj

    def _setup(self, hint, hdrsize_b, logsize_b):
        self._hdr = _hdr_t.from_buffer(self._mobj)
        if (self._hdr.rev != _HDR_REVISION or
            self._hdr.hdrsize != hdrsize_b or
            self._hdr.logsize != logsize_b):
            self._hdr.clear()
            self._hdr.rev = _HDR_REVISION
            self._hdr.hdrsize = hdrsize_b
            self._hdr.logsize = logsize_b
            if hint:
                self._hdr.hint = hint[:_HDR_HINTSIZE-1]
        if self._hdr.cnt == 0 and self._hdr.nextlnkaddr == 0:
            lnk = _lnk_t()
            lnk.prevlnkoff = self._hdr.logsize * 2
            self._rb.put(0, c_sizeof(lnk), lnk)

    def __new__(cls, path, hint, hdrsize_b, logsize_b):
        self = super(_RlogWriter, cls).__new__(cls)
        ch_size = tb.alignP2(c_sizeof(_hdr_t), 16)
        self._mmapsize = ch_size + hdrsize_b + logsize_b
        self._maxdsize = logsize_b - 2 * c_sizeof(_lnk_t)
        if not self._mmap(path):
            return tb.Null
        self._rb = _Rbuf(self._mobj, ch_size + hdrsize_b, logsize_b)
        self._setup(hint, hdrsize_b, logsize_b)
        #
        self._buf_lnk = _lnk_t()
        self._buf_plnk = _lnk_t()
        return self

    def _setuplnk(self, dsize):
        prevlnkaddr = self._hdr.nextlnkaddr
        t = time.time()
        self._hdr.cnt += 1
        lnksize = c_sizeof(_lnk_t)

        # put new link data (terminator) before data
        lnk = self._buf_lnk
        lnk.size = dsize
        lnk.snum = self._hdr.cnt
        lnk.tvsec = int(t)
        lnk.tvusec = int((t - lnk.tvsec) * 1000000)
        lnk.prevlnkoff = lnksize + dsize
        lnk.nextlnkoff = 0					# terminate
        addr = self._hdr.nextlnkaddr + lnksize + dsize
        self._rb.put(addr, lnksize, lnk)
        self._hdr.nextlnkaddr = addr

        # update previous link data
        plnk = self._buf_plnk
        self._rb.get(prevlnkaddr, lnksize, plnk)
        lnk.prevlnkoff = plnk.prevlnkoff
        lnk.nextlnkoff = self._hdr.nextlnkaddr - prevlnkaddr	# not terminate
        self._rb.put(prevlnkaddr, lnksize, lnk)

        # address of data store
        return prevlnkaddr + lnksize

    def put(self, s, size_b):
        if size_b > self._maxdsize:
            return
        addr = self._setuplnk(size_b)
        self._rb.put(addr, size_b, s)
        self._hdr.nextlnkaddr %= self._hdr.logsize

class _RlogScanner(object):

    def __init__(self, path):
        with open(path) as f:
            buf = bytearray(f.read())
        ch_size = tb.alignP2(c_sizeof(_hdr_t), 16)
        self._hdr = _hdr_t.from_buffer(buf)
        self._rb = _Rbuf(buf, ch_size + self._hdr.hdrsize, self._hdr.logsize)
        self.tmv_range = (0, time.time())
        self.sno_range = (0, self._hdr.cnt)

    def _beyond_first(self, lnk):
        return (lnk.tvsec < self.tmv_range[0] or
                lnk.snum  < self.sno_range[0])

    def _beyond_last(self, lnk):
        return (lnk.tvsec > self.tmv_range[1] or
                lnk.snum  > self.sno_range[1])

    def _findstartaddr(self):
        lnk = _lnk_t()
        lnksize = c_sizeof(lnk)
        rewindsize = c_sizeof(lnk)
        lnkaddr = self._hdr.nextlnkaddr + self._hdr.logsize * 2
        while True:
            self._rb.get(lnkaddr, lnksize, lnk)
            rewindsize += lnk.prevlnkoff
            if rewindsize > self._hdr.logsize:
                break
            if self._beyond_first(lnk):
                lnkaddr += lnk.nextlnkoff
                break
            if lnk.prevlnkoff <= 0:
                break
            lnkaddr -= lnk.prevlnkoff
        return lnkaddr

    def __iter__(self):
        lnk = _lnk_t()
        lnksize = c_sizeof(lnk)
        addr = self._findstartaddr()
        cbuf = (c_char*8192)()
        while True:
            self._rb.get(addr, lnksize, lnk)
            if lnk.nextlnkoff == 0:
                break
            if self._beyond_last(lnk):
                break
            addr += lnksize
            if lnk.size > c_sizeof(cbuf):
                cbuf = (c_char * tb.alignP2(lnk.size, 1024))()
            self._rb.get(addr, lnk.size, cbuf)
            addr += lnk.size
            yield (lnk, cbuf)

#----------------------------------------------------------------------------
#                           rlog logger interface
#----------------------------------------------------------------------------

class Rlog(object):

    _c_lock = tu.Lock()
    _c_rdic = {}		# dict of (lock, c-rlog)

    def __init__(self, path, logsize_kb, pref='', hint='default', hdrsize_b=0):
        if not path.endswith('.rlog'):
            path += '.rlog'
        path = os.path.realpath(os.path.expandvars(os.path.expanduser(path)))
        self._pref = pref
        self._hold = ''

        with self._c_lock:
            if path in self._c_rdic:
                self._i_lock, self._rl = self._c_rdic[path]
            else:
                self._i_lock = tu.Lock()
                self._rl = _RlogWriter(path, hint, hdrsize_b, logsize_kb*1024)
                self._c_rdic[path] = (self._i_lock, self._rl)

    def __call__(self, *args):
        self.put(*args)

    def putraw(self, s, size_b):
        if self._rl:
            with self._i_lock:
                self._rl.put(s, size_b)

    def put(self, format, *args):
        p = self._pref+': '
        s = p + (format % args).replace('\n', '\n'+p) + '\n\0'
        self.putraw(s, len(s))

    def write(self, s):
        if self._rl:
            with self._i_lock:
                if s == '':
                    pass
                elif s[-1] != '\n':
                    self._hold += s
                else:
                    self._hold += (s + '\0')
                    self._rl.put(self._hold, len(self._hold))
                    self._hold = ''

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []

if __name__ == '__main__':
    import argparse
    import re
    
    class DateSpec(object):
        def __init__(self):
            # match.group(N)  N: 3:YY, 4:MM, 5:DD, 6:hh, 7:mm
            self._YYMMDDhhmm = re.compile(r'^(((\d\d)?(\d\d))?(\d\d))?(\d\d)(\d\d)$')

        def time(self, spec):
            tm = list(time.localtime())
            m = re.match(self._YYMMDDhhmm, spec)
            for re_index, tm_index, v_min, v_max, tm_off, tm_type in [
                (3, 0,  0, 99, 2000, 'year'),
                (4, 1,  1, 12,    0, 'month'),
                (5, 2,  1, 31,    0, 'day'),
                (6, 3,  0, 23,    0, 'hour'),
                (7, 4,  0, 59,    0, 'minute')]:
                v = m.group(re_index)
                if v:
                    v = int(v)
                    if not (v_min <= v <= v_max):
                        raise Exception('Specified %s "%d" is out of range' %
                                        (tm_type, v))
                    tm[tm_index] = tm_off + v
            tm[5] = 0
            return int(time.mktime(tm))

    parser = argparse.ArgumentParser()
    parser.add_argument('logname', type=str, help='Rlog name')
    parser.add_argument('-l', dest='tail', type=int, default=100,
                        help='number of log from tail')
    parser.add_argument('-i', dest='min_sno', type=int,
                        help='minimum sequence number')
    parser.add_argument('-I', dest='max_sno', type=int,
                        help='maximum sequence number')
    parser.add_argument('-d', dest='min_date', type=str,
                        help='minimum date ([[[YY]MM]DD]hhmm)')
    parser.add_argument('-D', dest='max_date', type=str,
                        help='maximum date ([[[YY]MM]DD]hhmm)')
    prm = parser.parse_args()

    path = prm.logname
    if '/' not in path:
        path = '.' + path
    path = tb.fn.find(tb.fn.add_suffix(path, '.rlog'),
                      'RLOG_PATH', ['~/', '/var/log'])
    rlscan = _RlogScanner(path)

    smin, smax = rlscan.sno_range
    tmin, tmax = rlscan.tmv_range

    if (prm.min_sno is None and prm.max_sno is None and
        prm.min_date is None and prm.max_date is None):
        if prm.tail > 0:
            smin = smax - prm.tail + 1
    else:
        if prm.min_sno is not None:
            smin = max(smin, prm.min_sno)
        if prm.max_sno is not None:
            smax = min(smax, prm.max_sno)
        dspec = DateSpec()
        if prm.min_date:
            tmin = max(tmin, dspec.time(prm.min_date))
        if prm.max_date:
            tmax = min(tmax, dspec.time(prm.max_date) + 60)

    rlscan.sno_range = (smin, smax)
    rlscan.tmv_range = (tmin, tmax)

    try:
        for lnk, s in rlscan:
            pref = time.strftime('%%5d %m/%d %H:%M:%S.%%06d:', time.localtime(lnk.tvsec))
            pref = pref % (lnk.snum, lnk.tvusec)
            for s in s[:lnk.size-2].split('\n'):
                print pref, s
    except:
        pass
