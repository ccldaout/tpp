import time
import gc
from tpp import task
from tpp import threadutil as tu
from tpp.threadutil import pr, test_cancel

pr.print_name = True

def act(name, intv_s, cnt):
    def clean():
        pr('act:%s ... cancled', name)
    pr('act:%s ... start', name)
    for n in range(cnt):
        pr('act:%s ... %d/%d', name, n, cnt)
        time.sleep(intv_s)
        if name == '##':
            cnt = itv		# ERROR
        test_cancel(clean)
    pr('act:%s ... end', name)
    return intv_s * cnt

t1 = task.Action(act, '#1', 1.0, 5)
t2 = task.Action(act, '#2', 1.1, 5)
t3 = task.Action(act, '#3', 0.7, 4)
t4 = task.Action(act, '#4', 0.2, 2)
t5 = task.Action(act, '#5', 0.3, 2)
t6 = task.Action(act, '#6', 1.5, 3)
t7 = task.Action(act, '#7', 1.0, 2)

if False:
    t = task.Sequence(task.All(task.Any(t1, t2, t3),
                               task.Sequence(t4, t5),
                               t6),
                      t7)
else:
    t = ((t1|t2|t3) & (t4+t5) & t6) + t7

pr('main ... starting')
t.start(tu.ThreadPool(thread_max=3).start())
pr('main ... started')
r = t.result
pr('main ... result: %s', r)
if r.success:
    print 'r.result[0].result[1].result[1].result (#5)', r.result[0].result[1].result[1].result
    print 'r[0][1][1].result (#5)', r[0][1][1].result
t = None
print 'gc.collect:', gc.collect()
