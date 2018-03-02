# -*- coding: utf-8 -*-

import select

if hasattr(select, 'epoll'):

    POLLIN = select.EPOLLIN
    POLLOUT = select.EPOLLOUT
    POLLERR = select.EPOLLERR
    POLLHUP = select.EPOLLHUP

    class poll(object):
        def __init__(self):
            self._fobjs = {}
            self._poll = select.epoll()

        def register(self, fobj, eventmask):
            fd = fobj.fileno()
            self._fobjs[fd] = fobj
            self._poll.register(fd, eventmask)

        def unregister(self, fobj):
            fd = fobj.fileno()
            if fd in self._fobjs:
                del self._fobjs[fd]
                self._poll.unregister(fd)

        def ipoll(self, timeout=-1):
            fds = self._poll.poll(timeout)
            if timeout and not fds:
                return
            for fd, flag in fds:
                yield (self._fobjs[fd], flag)

        def poll(self, timeout=-1):
            return self._poll.poll(timeout)

else:

    import os
    import Queue

    POLLIN = select.POLLIN
    POLLOUT = select.POLLIN
    POLLERR = select.POLLERR|select.POLLNVAL
    POLLHUP = select.POLLHUP

    class poll(object):
        def __init__(self):
            self._fobjs = {}
            self._poll = select.poll()
            self._notify_pipe = os.pipe()
            self._notify_data = bytearray(1)
            self._poll.register(self._notify_pipe[0], POLLIN)
            self._reqque = Queue.Queue()

        def _register(self, fd, fobj, eventmask):
            self._poll.register(fd, eventmask)
            self._fobjs[fd] = fobj

        def _unregister(self, fd):
            if fd in self._fobjs:
                del self._fobjs[fd]
                self._poll.unregister(fd)

        def register(self, fobj, eventmask):
            self._reqque.put((self._register, (fobj.fileno(), fobj, eventmask)))
            os.write(self._notify_pipe[1], self._notify_data)

        def unregister(self, fobj):
            self._reqque.put((self._unregister, (fobj.fileno(),)))
            os.write(self._notify_pipe[1], self._notify_data)

        def ipoll(self, timeout=-1):
            fds = self._poll.poll(timeout)
            if timeout and not fds:
                return
            for fd, flag in fds:
                if fd == self._notify_pipe[0]:
                    os.read(self._notify_pipe[0], 1)
                    func, args = self._reqque.get()
                    func(*args)
                else:
                    if fd in self._fobjs:
                        yield (self._fobjs[fd], flag)
                    else:
                        print 'fd:%1d is not registerd (maybe closed).' % fd

        def poll(self, timeout=-1):
            return list(self.ipoll(timeout))
