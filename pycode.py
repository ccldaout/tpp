# -*- coding: utf-8 -*-

import dis
import marshal
import types

def dis_code(c, upper=None):
    if isinstance(c, types.FunctionType):
        c = c.__code__
    if upper is None:
        upper = c.co_name
    else:
        upper = upper + '.' + c.co_name
    for c2 in c.co_consts:
        if isinstance(c2, types.CodeType):
            dis_code(c2, upper)
            print
    print '[ co_name: %s ] --------' % upper, c
    print '  co_varnames :', c.co_varnames
    print '  co_names    :', c.co_names
    print '  co_freevars :', c.co_freevars
    print '  co_cellvars :', c.co_cellvars
    print '  co_flags    : 0o%o' % c.co_flags 
    dis.dis(c)

def dis_pyc(pyc):
     with open(pyc, 'rb') as f:
         dis_code(marshal.loads(f.read()[8:]), '')

def dis_py(py):
    with open(py) as f:
        dis_code(compile(f.read(), py, 'exec'), '')

if __name__ == '__main__':
    import sys
    f = sys.argv[1]
    if f.endswith('.py'):
        dis_py(f)
    elif f.endswith(('.pyc', '.pyo')):
        dis_pyc(f)
