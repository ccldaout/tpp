# -*- coding: utf-8 -*-

import ctypes
from ctypes import (c_void_p,
                    c_char_p,
                    c_char,
                    c_short,
                    c_ushort,
                    c_int,
                    c_uint,
                    c_long,
                    c_ulong,
                    c_size_t,
                    c_int8,
                    c_uint8,
                    c_int16,
                    c_uint16,
                    c_int32,
                    c_uint32,
                    c_int64,
                    c_uint64,
                    c_float,
                    c_double)

c_ssize_t = c_long
c_POINTER = ctypes.POINTER
c_pointer = ctypes.pointer
c_byref = ctypes.byref
c_sizeof = ctypes.sizeof
c_addressof = ctypes.addressof
c_cast = ctypes.cast
c_memmove = ctypes.memmove
c_memset = ctypes.memset
c_string_at = ctypes.string_at
