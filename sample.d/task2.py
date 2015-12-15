# -*- coding: utf-8 -*-

import time
from tpp import threadutil as tu
from tpp.task import DAGTasks

pr = tu.pr
pr.print_name = True

def act(node, w_s=None):
    tu.pr('act: %s ...', node.key)
    if w_s:
        time.sleep(w_s)
    tu.pr('act: %s ... end', node.key)

dag = DAGTasks()

tasklist = [
    # (target, (source, ...), duration), ...
    ('prog', ('main.o', 'sub1.o', 'sub2.o', 'lib.so'), 3.0),
    ('main.o', ('main.c', 'prog.h', 'lib.h'), 2.0),
    ('sub1.o', ('sub1.c', 'prog.h'), 0.5),
    ('sub2.o', ('sub2.c', 'lib.h'), 0.6),
    ('lib.so', ('liba.o', 'libb.o'), 0.4),
    ('liba.o', ('liba.c', 'lib.h'), 0.3),
    ('libb.o', ('libb.c', 'lib.h'), 0.7),
    ]
for target, sources, duration in tasklist:
    tn = dag.node(target, action=act)
    tn.args = (duration,)
    for source in sources:
        sn = dag.node(source, action=act)
        tn.depend_on(sn)

dag.start(tu.ThreadPool(thread_max=3))
dag.wait()
