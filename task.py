# -*- coding: utf-8 -*-

from tpp import threadutil as tu

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

    def __new__(cls, ini_result = None):
        self = super(_TaskBase, cls).__new__(cls)
        self.__is_started = tu.Event()
        self.__is_finished = tu.Event()
        self.__boss = None
        self._i_lock = tu.Lock()
        self._result = TaskResult(self, False, ini_result)
        self.threadpool = None
        return self

    # DON'T override

    def __prologue(self, boss):
        if self.__is_started.is_set():
            raise RuntimeError('Task is already started.')
        self.__is_started.set()
        self.__boss = boss

    def start(self, threadpool=None, boss=None):
        if threadpool:
            self.threadpool = threadpool
        elif boss:
            self.threadpool = boss.threadpool
        else:
            self.threadpool = tu.threadpool
        self.__prologue(boss)
        self._start()
        return self

    def _epilogue(self):
        self.__is_finished.set()
        if self.__boss:
            self.__boss._handle_end(self._result)
            self.__boss = None	# to avoid remaining cyclic reference

    def wait(self):
        self.__is_finished.wait()

    @property
    def result(self):
        self.wait()
        return self._result

    # NEED override

    def _start(self):
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
        self = super(_TaskSequence, cls).__new__(cls, [])
        self._tasks = list(tasks)
        self._last_task = tasks[-1]
        self._running_task = None
        return self

    def _start(self):
        if self._tasks:
            t = self._tasks.pop(0)
            t.start(boss=self)
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
                t.start(boss=self)
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
        self = super(_TaskAll, cls).__new__(cls, ini_result)
        self._tasks_ordered = tasks
        self._tasks = set(tasks)
        return self

    def _start(self):
        self._result.success = True
        for t in self._tasks:
            t.start(boss=self)

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
        self = super(_TaskAny, cls).__new__(cls)
        self._tasks = set(tasks)
        return self

    def _start(self):
        for t in self._tasks:
            t.start(boss=self)

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

__all__ = []

if __name__ == '__main__':
    pass
