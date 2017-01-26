# -*- coding: utf-8 -*-

from tpp import threadutil as tu
import inspect
import Queue
import select
import traceback
import types

class _AsyncReturn(object):

    __slots__ = ('val',)

    def __new__(cls, val):
        self = super(_AsyncReturn, cls).__new__(cls)
        self.val = val
        return self

class _AsyncObject(object):

    __slots__ = ('__action', '__call__')

    def __new__(cls, func, *args, **kwargs):
        self = super(_AsyncObject, cls).__new__(cls)
        self.__action = (func, args, kwargs)
        return self

    def __call__(self):
        try:
            f, args, kwargs = self.__action
            return f(*args, **kwargs)
        except Exception as e:
            return e

class _Driver(object):

    def __new__(cls, threadpool=tu.threadpool):
        self = super(_Driver, cls).__new__(cls)
        self.__threadpool = threadpool
        self.__event_queue = Queue.Queue()
        self.__parent_generator = {}
        self.__driver_thread = None
        return self

    def __drive_loop(self):
        next_gen = None
        next_val = None
        while True:
            gen, next_gen = next_gen, None
            val, next_val = next_val, None
            try:
                if gen is None:
                    gen, val = self.__event_queue.get()
                    if gen is None:
                        return
                if isinstance(val, Exception):
                    step = gen.throw(val)
                else:
                    step = gen.send(val)
                if isinstance(step, types.GeneratorType):
                    self.__parent_generator[step] = gen
                    next_gen = step
                elif isinstance(step, _AsyncReturn):
                    next_gen = self.__parent_generator.pop(gen, None)
                    next_val = step.val
                elif isinstance(step, _AsyncObject):
                    self.__threadpool.queue(self.__call_async, gen, step)
                else:
                    next_gen = gen
                    next_val = TypeError('Must yield async.call() or async.return_() or generator')
            except Exception as e:
                next_gen = self.__parent_generator.pop(gen, None)
                if not isinstance(e, StopIteration):
                    traceback.print_exc()
                    if next_gen:
                        next_val = e

    def __call_async(self, gen, aobj):
        val = aobj()
        self.__event_queue.put((gen, val))

    def start(self, daemon=True):
        self.__driver_thread = tu.Thread(target=self.__drive_loop)
        self.__driver_thread.name = 'async.driver'
        self.__driver_thread.daemon = daemon
        self.__driver_thread.start()
        return self

    def spool(self, func, *args, **kwargs):
        if not inspect.isgeneratorfunction(func):
            raise TypeError('1st argument of spool must be generator function')
        self.__event_queue.put((func(*args, **kwargs), None))
        return self

    def stop(self):
        self.__event_queue.put((None, None))

    def wait(self, tmo_s = None):
        self.__driver_thread.join(tmo_s)

_default_driver = _Driver()
start = _default_driver.start
spool = _default_driver.spool
stop = _default_driver.stop
wait = _default_driver.wait

return_ = _AsyncReturn
call = _AsyncObject

def handler(func):
    '''async handler decorator'''
    if inspect.isgeneratorfunction(func):
        return func
    def _handler(*args, **kwargs):
        yield return_(func(*args, **kwargs))
    _handler.__name__ = func.__name__
    _handler.__doc__ = func.__doc__
    return _handler

__all__ = []
