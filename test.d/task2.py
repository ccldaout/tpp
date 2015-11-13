import time
import gc
from tpp import task
from tpp.threadutil import pr, test_cancel

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

t = task.Sequence(task.All(task.Any(task.Action(act, '#1', 1.0, 5),
                                    task.Action(act, '#2', 1.1, 5),
                                    task.Action(act, '#3', 0.7, 4)),
                           task.Sequence(task.Action(act, '#4', 0.2, 2),
                                         task.Action(act, '#5', 0.3, 2)),
                           task.Action(act, '#6', 1.5, 3)),
                  task.Action(act, '#7', 1.0, 2))

pr('main ... starting')
t.start()
pr('main ... started')
r = t.result
pr('main ... result: %s', r)
if r.success:
    print 'r.result[0].result[1].result[1].result (#5)', r.result[0].result[1].result[1].result
    print 'r[0][1][1].result (#5)', r[0][1][1].result
t = None
print 'gc.collect:', gc.collect()
