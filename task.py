# -*- coding: utf-8 -*-

import traceback
from tpp import threadutil as tu

#----------------------------------------------------------------------------
#                              Task Operation
#----------------------------------------------------------------------------

class TaskResult(object):
    def __new__(cls, terminated_task, success, result):
        self = super(TaskResult, cls).__new__(cls)
        self.task = terminated_task
        self.success = success
        self.result = result
        return self

    def __str__(self):
        return str((self.task, self.success, self.result))

    __repr__ = __str__

    def __getitem__(self, idx):
        return self.result[idx]

class _TaskBase(object):
    def __new__(cls, ini_result=None, tasks=()):
        self = super(_TaskBase, cls).__new__(cls)
        for t in tasks:
            t.__add_boss(self)
        self.__is_started = tu.Event()
        self.__is_finished = tu.Event()
        self.__boss = []
        self._i_lock = tu.Lock()
        self._result = TaskResult(self, False, ini_result)
        self.threadpool = None
        return self

    # DON'T override

    def __or__(self, other):
        if isinstance(self, _TaskAny):
            return self.__add_operand(other)
        return _TaskAny(self, other)

    def __and__(self, other):
        if isinstance(self, _TaskAll):
            return self.__add_operand(other)
        return _TaskAll(self, other)

    def __add__(self, other):
        if isinstance(self, _TaskSequence):
            return self.__add_operand(other)
        return _TaskSequence(self, other)

    def start(self, threadpool=None):
        if threadpool:
            self.threadpool = threadpool
        else:
            self.threadpool = tu.threadpool
        if self.__is_started.is_set():
            return self
        self.__is_started.set()
        self._start()
        return self

    def __add_operand(self, other):
        self._add_operand(other)
        other.__add_boss(self)
        return self

    def __add_boss(self, boss):
        self.__boss.append(boss)

    def _epilogue(self):
        self.__is_finished.set()
        boss = self.__boss
        self.__boss = ()
        for b in boss:
            b._handle_end(self._result)

    def wait(self):
        self.__is_finished.wait()

    @property
    def result(self):
        self.wait()
        return self._result

    # NEED override

    def _start(self):
        raise NotImplementedError()

    def _add_operand(self, other):
        raise NotImplementedError()

    def _handle_end(self, task_result):
        raise NotImplementedError()

    def abort(self):
        raise NotImplementedError()

class _TaskAction(_TaskBase):
    def __new__(cls, func, *args, **kwargs):
        self = super(_TaskAction, cls).__new__(cls)
        self.__act = (func, args, kwargs)
        self.__thread = None
        self.__cancel = False
        return self

    def __action(self):
        func, args, kwargs = self.__act
        try:
            with self._i_lock:
                if self.__cancel:
                    raise tu.Canceled()
                self.__thread = tu.current_thread()
            result = func(*args, **kwargs)
            self._result.success = True
            self._result.result = result
        except Exception as e:
            self._result.result = e
        self._epilogue()

    def _start(self):
        self.threadpool.queue(self.__action)

    def abort(self):
        with self._i_lock:
            if self.__thread:
                self.__thread.cancel()
            else:
                self.__cancel = True

class _TaskSequence(_TaskBase):
    def __new__(cls, *tasks):
        self = super(_TaskSequence, cls).__new__(cls, [], tasks)
        self._tasks = list(tasks)
        self._last_task = tasks[-1]
        self._running_task = None
        return self

    def _add_operand(self, task):
        self._tasks.append(task)
        self._last_task = task

    def _start(self):
        if self._tasks:
            t = self._tasks.pop(0)
            t.start(self.threadpool)
            self._running_task = t
        else:
            self._epilogue()

    def _handle_end(self, task_result):
        with self._i_lock:
            self._running_task = None
            self._result.result.append(task_result)
            if not task_result.success:
                self._tasks = None
            if self._tasks:
                t = self._tasks.pop(0)
                t.start(self.threadpool)
                self._running_task = t
                return
        if self._last_task == task_result.task and task_result.success:
            self._result.success = True
        self._epilogue()

    def abort(self):
        with self._i_lock:
            if self._running_task:
                self._running_task.abort()
            self._tasks = None

class _TaskAll(_TaskBase):
    def __new__(cls, *tasks):
        ini_result = [None] * len(tasks)
        self = super(_TaskAll, cls).__new__(cls, ini_result, tasks)
        self._tasks_ordered = list(tasks)
        self._tasks = set(tasks)
        return self

    def _add_operand(self, task):
        self._tasks_ordered.append(task)
        self._tasks.add(task)
        self._result.result.append(None)

    def _start(self):
        self._result.success = True
        for t in self._tasks:
            t.start(self.threadpool)

    def _handle_end(self, task_result):
        with self._i_lock:
            taskidx = self._tasks_ordered.index(task_result.task)
            self._result.result[taskidx] = task_result
            self._tasks.remove(task_result.task)
            if not task_result.success:
                self._result.success = False
                for t in self._tasks:
                    t.abort()
            if self._tasks:
                return
        self._epilogue()

    def abort(self):
        with self._i_lock:
            for t in self._tasks:
                t.abort()

class _TaskAny(_TaskBase):
    def __new__(cls, *tasks):
        self = super(_TaskAny, cls).__new__(cls, tasks=tasks)
        self._tasks = set(tasks)
        return self

    def _add_operand(self, task):
        self._tasks.add(task)

    def _start(self):
        for t in self._tasks:
            t.start(self.threadpool)

    def _handle_end(self, task_result):
        do_epilogue = False
        with self._i_lock:
            if self._tasks:
                if task_result.task in self._tasks:
                    self._tasks.remove(task_result.task)
                if task_result.success:
                    for t in self._tasks:
                        t.abort()
                    self._result.success = True
                    self._result.result = task_result
                    self._tasks = None
                if not self._tasks:
                    do_epilogue = True
        if do_epilogue:
            self._epilogue()

    def abort(self):
        with self._i_lock:
            for t in self._tasks:
                t.abort()

def Action(func, *args, **kwargs):
    return _TaskAction(func, *args, **kwargs)

def Sequence(*tasks):
    return _TaskSequence(*tasks)

def All(*tasks):
    return _TaskAll(*tasks)

def Any(*tasks):
    return _TaskAny(*tasks)

#----------------------------------------------------------------------------
#                   DAG (Directed Acylic Graph) type task
#----------------------------------------------------------------------------

class DAGNode(object):
    _c_lock = tu.Lock()

    def __new__(cls):
        self = super(DAGNode, cls).__new__(cls)
        self._depended_by = set([])
        self._depend_on = set([])
        self._depend_on_cd = 0
        self.key = None
        self.action = None	# action(node, *args, **kwargs)
        self.args = None
        self.kwargs = None
        self.data = None
        self.status = None	# True/False/None
        return self

    def depend_on(self, *nodes):
        for n in nodes:
            if n not in self._depend_on:
                self._depend_on.add(n)
            if self not in n._depended_by:
                n._depended_by.add(self)
        self._depend_on_cd = len(self._depend_on)
        return tuple(self._depend_on)

    def is_startpoint(self):
        return not bool(self._depend_on)

    def is_endpoint(self):
        return not bool(self._depended_by)

    def do(self, dag):
        for n in self._depend_on:
            if n.status is not True:
                break
        else:
            try:
                args = self.args if self.args else ()
                kwargs = self.kwargs if self.kwargs else {}
                self.action(self, *args, **kwargs)
                self.status = True
            except:
                traceback.print_exc()
                self.status = False
                dag.error(self)
        with self._c_lock:
            for n in self._depended_by:
                n._depend_on_cd -= 1
                if n._depend_on_cd == 0:
                    dag.queue(n)
            
class DAGTasks(object):
    def __new__(cls):
        self = super(DAGTasks, cls).__new__(cls)
        self._kndic = {}
        self._nodes = []
        self._root = DAGNode()
        self._threadpool = None
        self.stop_if_error = True
        return self

    def node(self, key=None, action=None, args=None, kwargs=None, data=None):
        if key in self._kndic:
            return self._kndic[key]
        n = DAGNode()
        n.key = key
        n.action = action
        n.args = args
        n.kwargs = kwargs
        n.data = data
        self._nodes.append(n)
        if key is not None:
            self._kndic[key] = n
        return n

    def verify(self):
        ns = {}
        for n in self._nodes:
            ns[n] = set(n.depend_on())
        while True:
            rmc = 0
            for n, depon in ns.items():
                if not depon:
                    del ns[n]
                    rmc += 1
                    for n2, depon2 in ns.iteritems():
                        if n in depon2:
                            depon2.remove(n)
            if rmc == 0:
                break
        if ns:
            raise Exception('Task dependencies has some loops.')

    def start(self, threadpool):
        self.verify()
        self._threadpool = threadpool
        self._threadpool.start()
        for n in self._nodes:
            if n.is_endpoint():
                self._root.depend_on(n)
        for n in self._nodes:
            if n.is_startpoint():
                self._threadpool.queue(n.do, self)

    def queue(self, node):
        if node is self._root:
            self._threadpool.end(soon=True)
        else:
            self._threadpool.queue(node.do, self)

    def error(self, node):
        if self.stop_if_error:
            self._threadpool.end(soon=True)

    def wait(self):
        self._threadpool.wait()

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []

if __name__ == '__main__':
    pass
