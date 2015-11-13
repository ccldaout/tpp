import tpp.threadutil as tu

class _TaskNode(object):

    FREE = 0
    QUEUED = 1
    SUCCESS = 2
    FAILURE = 3
    CANCEL = 4

    def __new__(cls):
        self = super(_TaskNode, cls).__new__(cls)
        self.action = None
        self._refby = set([])	# nodes who depend on self
        self._refto = set([])	# nodes that self depend on
        self.status = _TaskNode.FREE
        return self

    def set_action(self, func, *args, **kw):
        self.action = lambda:func(*args, **kw)

    def ref_by(self, node = None):
        if node and node not in self._refby:
            self._refby.add(node)
            node._refto.add(self)
        return self._refby
            
    def ref_to(self, node = None):
        if node and node not in self._refto:
            self._refto.add(node)
            node._refby.add(self)
        return self._refto

class TaskGraph(object):
    def __new__(cls, threadpool):
        self = super(TaskGraph, cls).__new__(cls)
        self._lock = tu.Lock()
        self._nodedic = {}
        self._tpool = threadpool
        self._abort_if_err = False
        self._terminate = _TaskNode()
        return self

    def get_node(self, key):
        if key not in self._nodedic:
            self._nodedic[key] = _TaskNode()
        return self._nodedic[key]

    def __iter__(self):
        return self._nodedic.iteritems()

    def _queue(self, node):
        node.status = _TaskNode.QUEUED
        self._tpool.queue(self._do_action, node)

    def _do_action(self, node):
        if node == self._terminate:
            self._tpool.end()
            return
        if all((c.status == _TaskNode.SUCCESS for c in node.ref_to())):
            s = _TaskNode.SUCCESS if node.action() else _TaskNode.FAILURE
        else:
            s = _TaskNode.CANCEL
        with self._lock:
            node.status = s
            if s == _TaskNode.FAILURE and self._abort_if_err:
                self._tpool.end(soon = True)
                return
            for p in (p for p in node.ref_by() if p.status == _TaskNode.FREE):
                if all((c.status not in (_TaskNode.FREE, _TaskNode.QUEUED)
                        for c in p.ref_to())):
                    self._queue(p)

    def start(self, abort_if_err = False):
        self._tpool.start()
        self._abort_if_err = abort_if_err
        for n in self._nodedic.itervalues():
            if not n.ref_by():
                n.ref_by(self._terminate)
            if not n.ref_to():
                self._queue(n)

    def wait(self):
        self._tpool.wait()

if __name__ == '__main__':
    import time
    from tpp.threadutil import pr, ThreadPool

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

    def _action(target, duraiton):
        pr('%s %s ... %f', tu.currentThread().name, target, duration)
        time.sleep(duration)
        pr('%s %s ... end', tu.currentThread().name, target)
        return True

    graph = TaskGraph(ThreadPool(thread_max=4))
    for trg, srcs, duration in tasklist:
        tnode = graph.get_node(trg)
        tnode.set_action(_action, trg, duration)
        for src in srcs:
            snode = graph.get_node(src)
            if snode.action is None:
                snode.action = lambda:True
            tnode.ref_to(snode)	    # tnode depend on snode.
    graph.start()
    graph.wait()
