# -*- coding: utf-8 -*-

import threading
import time
import traceback
from threading import *
from tpp import toolbox as tb

pr = tb.pr			# for compatibility

#-----------------------------------------------------------------------------
#                 Extend class to avoid blocking main thread
#-----------------------------------------------------------------------------

_tmo_s = 3600*24*365*100

class Canceled(Exception):
    pass

def test_cancel(cleaner=None):
    t = threading.current_thread()
    if t._canceling.is_set():
        if cleaner:
            cleaner()
        raise Canceled()

def Thread(**kwargs):
    def join_wrapper(thr, orgjoin):
        def join(timeout=None):
            tmo_s = timeout if timeout else _tmo_s
            while thr.is_alive():
                orgjoin(tmo_s)
                if timeout:
                    break
            return not thr.is_alive()
        return join
    t = threading.Thread(**kwargs)
    t.join = join_wrapper(t, t.join)
    t._canceling = threading.Event()
    t.cancel = (lambda thr: lambda: thr._canceling.set())(t)
    return t

class Condition(type(threading.Condition())):
    def wait(self, timeout=None):
        tmo_s = timeout if timeout else _tmo_s
        lim_s = time.time() + tmo_s
        while True:
            super(Condition, self).wait(tmo_s)
            if time.time() < lim_s:
                return True
            if timeout:
                return False

class Event(type(threading.Event())):
    def wait(self, timeout=None):
        tmo_s = timeout if timeout else _tmo_s
        while True:
            super(Event, self).wait(tmo_s)
            if self.is_set():
                return True
            if timeout:
                return False

#-----------------------------------------------------------------------------
#                              Cancelable queue
#-----------------------------------------------------------------------------

class Queue(object):
    def __new__(cls, value_in_tmo = None, value_in_stopped = False):
        self = super(Queue, cls).__new__(cls)
        self._list = []
        self._cond = Condition()
        self._value_in_tmo = value_in_tmo
        self._value_in_stopped = value_in_stopped
        self._stopped = False
        return self

    def put(self, data):
        with self._cond:
            if self._stopped:
                raise RuntimeError('Queue.stop is already called.')
            self._list.append(data)
            self._cond.notify_all()
            return self

    def get(self, tmo_s = _tmo_s):
        with self._cond:
            while not self._list:
                if not self._cond.wait(tmo_s):
                    return self._value_in_tmo
            data = self._list.pop(0)
            if data is self._value_in_stopped:
                self._list = [data]
            return data

    def stop(self, soon=False):
        with self._cond:
            if soon:
                self.clear()
            self.put(self._value_in_stopped)
            self._stopped = True

    def clear(self):
        with self._cond:
            self._list = []
            self._stopped = False

#-----------------------------------------------------------------------------
#                                Thread pool
#-----------------------------------------------------------------------------

class ThreadPool(object):
    _g_lock = threading.Lock()
    _g_count = 0

    thread_max = tb.SimpleProperty('_c_max')
    thread_lwm = tb.SimpleProperty('_c_lwm')
    thread_tmo = tb.SimpleProperty('_c_tmo')

    def __new__(cls, thread_max=8, thread_lwm=1, thread_tmo=120):
        self = super(ThreadPool, cls).__new__(cls)
        with cls._g_lock:
            self._name = 'POOL#%d' % cls._g_count
            cls._g_count += 1
        self._que = Queue(value_in_tmo = (False, None, None),
                          value_in_stopped = (None, None, None))
        self._lock = threading.Lock()
        self._no_worker = Event()
        self._available = False
        self._tid = 0
        self._c_que = 0
        self._c_cur = 0
        self._c_act = 0
        self._c_max = thread_max		# must be parameter
        self._c_lwm = thread_lwm
        self._c_tmo = thread_tmo
        return self
    
    def _worker_thread(self):
        self._no_worker.clear()
        while True:
            action, args, kwargs = self._que.get(self._c_tmo)
            if action is False:			# timeout
                with self._lock:
                    if self._c_cur > self._c_lwm:
                        self._c_cur -= 1
                        return
                continue
            if action is None:			# termination request
                with self._lock:
                    self._c_cur -= 1
                    if self._c_cur == 0:
                        self._no_worker.set()
                return

            with self._lock:
                self._c_act += 1
                self._c_que -= 1
            try:
                action(*args, **kwargs)
            except:
                traceback.print_exc()
            with self._lock:
                self._c_act -= 1

    def _add_thread(self):
        # require: self._lock must be locked by self.
        self._tid += 1
        t = Thread(target=self._worker_thread)
        t.name = '%s<%d>' % (self._name, self._tid)
        t.daemon = True
        t.start()

    def start(self):
        with self._lock:
            if not self._available:
                self._que.clear()
                self._available = True
        return self

    def queue(self, action, *args, **kwargs):
        if not callable(action):
            raise RuntimeError('1st argument must be callable.')
        with self._lock:
            if not self._available:
                raise RuntimeError('ThreadPool is now inactive.')
            if (self._c_cur < self._c_max and
                self._c_cur <= self._c_que + self._c_act):
                self._add_thread()
                self._c_cur += 1
            self._c_que += 1
        self._que.put((action, args, kwargs))
        return self

    def end(self, soon = False):
        with self._lock:
            self._available = False
        self._que.stop(soon)
        return self

    def wait(self):
        self._no_worker.wait()

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

threadpool = ThreadPool()
threadpool.start()

__all__ = []

if __name__ == '__main__':
    pass
