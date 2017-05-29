# -*- coding: utf-8 -*-

import collections
import math
import time
from tpp.validation import enforce_keyword
from tpp import threadutil as tu
from tpp import toolbox as tb
from tpp import ipc

LOG_SIZE = 30

class _Timestamp(object):
    __slots__ = ('tv',)
    format = '%H:%M:%S'

    def __init__(self):
        self.tv = time.time()

    def __repr__(self):
        fmt = self.format + '%%0.6f'
        return time.strftime(fmt, time.localtime(self.tv)) % math.modf(self.tv)[0]

class _ServiceBase(ipc.ServiceBase):

    def __new__(cls, logsize=None):
        self = super(_ServiceBase, cls).__new__(cls)
        self.quiet_messages = set()
        self.initlog(LOG_SIZE if logsize is None else logsize)
        self.on_message = self.__on_message
        return self

    def __on_message(self, msg):
        if not (True in self.quiet_messages or msg[0] in self.quiet_messages):
            tb.pr('%s', msg)

    def send(self, *args):
        raise NotImplementedError()

    def initlog(self, logsize):
        self.ipclog = collections.deque(maxlen=logsize)

    def log(self, direction, port_order, msg):
        self.ipclog.appendleft((_Timestamp(), direction, port_order, msg))

    def handle_default(self, port, msg):
        self.log(0, port.order, msg)
        self.on_message(msg)

    def handle_ACCEPTED(self, port):
        raise NotImplementedError()

    def handle_CONNECTED(self, port):
        raise NotImplementedError()

    def handle_DISCONNECTED(self, port):
        raise NotImplementedError()

    def handle_SOCKERROR(self, port):
        self.handle_DISCONNECTED(port)

class _ClientService(_ServiceBase):

    def __new__(cls, *args, **kws):
        self = super(_ClientService, cls).__new__(cls, *args, **kws)
        self.__port_ready = tu.Event()
        self.__port = None
        self.on_connected = lambda c:tb.pr('* #%1d connected *', c)
        self.on_disconnected = lambda c:tb.pr('* #%1d disconnected *', c)
        return self

    def handle_CONNECTED(self, port):
        self.log(0, port.order, ('*connected*',))
        self.__port = port
        self.__port_ready.set()
        self.on_connected(port.order)

    def handle_DISCONNECTED(self, port):
        self.log(0, port.order, ('*disconnected*',))
        self.__port_ready.clear()
        self.__port = None
        self.on_disconnected(port.order)

    def send(self, *args):
        self.log(1, self.__port.order, args)
        self.__port.send(args)

class _ServerService(_ServiceBase):

    def __new__(cls, *args, **kws):
        self = super(_ServerService, cls).__new__(cls, *args, **kws)
        self.__ports = {}
        self.on_connected = lambda c:tb.pr('* #%1d accepted *', c)
        self.on_disconnected = lambda c:tb.pr('* #%1d disconnected *', c)
        return self

    def handle_ACCEPTED(self, port):
        self.log(0, port.order, ('*accepted*',))
        self.__ports[port.order] = port
        self.on_connected(port.order)

    def handle_DISCONNECTED(self, port):
        self.log(0, port.order, ('*disconnected*',))
        del self.__ports[port.order]
        self.on_disconnected(port.order)

    def send(self, port_order, *args):
        if port_order not in self.__ports:
            raise KeyError('Invalid port_order argument: %s', port_order)
        self.log(1, port_order, args)
        self.__ports[port_order].send(args)

class _InteractiveBase(object):

    @enforce_keyword
    def __new__(cls, service,
                on_message=None, on_connected=None, on_disconnected=None,
                attr2ev=None, quiet_messages=None,
                logsize=None):
        if not isinstance(service, _ServiceBase):
            raise Exception('type of service parameter must be subclass of _ServiceBase')
        self = super(_InteractiveBase, cls).__new__(cls)
        self.__service = service
        if on_message:
            self.on_message = on_message
        if on_connected:
            self.on_connected = on_connected
        if on_disconnected:
            self.on_disconnected = on_disconnected
        if quiet_messages is not None:
            try:
                self.quiet_messages.update(quiet_messages)
            except:
                self.quiet_messages.add(quiet_messages)
        self.attr2ev = attr2ev if attr2ev else (lambda a:a)
        return self

    # customize

    @property
    def quiet_messages(self):
        return self.__service.quiet_messages

    # message sending

    def __call__(self, *args):
        return self.__service.send(*args)

    # message handling

    @property
    def on_message(self):
        return self.__service.on_message

    @on_message.setter
    def on_message(self, f):
        self.__service.on_message = f

    @property
    def on_connected(self):
        return self.__service.on_connected

    @on_connected.setter
    def on_connected(self, f):
        self.__service.on_connected = f

    @property
    def on_disconnected(self):
        return self.__service.on_disconnected

    @on_disconnected.setter
    def on_disconnected(self, f):
        self.__service.on_disconnected = f

    # message log

    def show(self):
        RW = ('R', 'W')
        log = self.__service.ipclog
        n = len(log)
        for i, (tms, rw, cid, msg) in reversed(list(enumerate(log))):
            print '%3d %s %s %2d %s' % (i, tms, RW[rw], cid, msg)

    def clear_history(self):
        self.__service.ipclog.clear()

    def resize_history(self, logsize):
        self.__service.initlog(logsize)

    def __getitem__(self, index):
        return self.__service.ipclog[index]

    def __iter__(self):
        return iter(self.__service.ipclog)

    def __len__(self):
        return len(self.__service.ipclog)

class InteractiveClient(_InteractiveBase):

    @enforce_keyword
    def __new__(cls, addr,
                packer=None, recover=True, retry=True,
                on_message=None, on_connected=None, on_disconnected=None,
                attr2ev=None, quiet_messages=None,
                logsize=None):
        service = _ClientService(logsize=logsize)
        self = super(InteractiveClient, cls).__new__(cls, service,
                                                     on_message=on_message,
                                                     on_connected=on_connected,
                                                     on_disconnected=on_disconnected,
                                                     attr2ev=attr2ev,
                                                     quiet_messages=quiet_messages)
        ipc.Connector(service, addr,
                      retry=retry, recover=recover, packer=packer).start()
        return self

    # message sending

    def __getattr__(self, attr):
        def sender(*args):
            args = (ev,) + args
            return self(*args)
        ev = self.attr2ev(attr)
        return sender

class InteractiveServer(_InteractiveBase):

    @enforce_keyword
    def __new__(cls, addr,
                packer=None,
                on_message=None, on_connected=None, on_disconnected=None,
                attr2ev=None, quiet_messages=None,
                logsize=None):
        service = _ServerService(logsize=logsize)
        self = super(InteractiveServer, cls).__new__(cls, service,
                                                     on_message=on_message,
                                                     on_connected=on_connected,
                                                     on_disconnected=on_disconnected,
                                                     attr2ev=attr2ev,
                                                     quiet_messages=quiet_messages)
        ipc.Acceptor(service, addr, packer_factory=packer).start()
        return self

    # message sending

    def __getattr__(self, attr):
        def sender(port_order, *args):
            args = (ev,) + args
            return self(port_order, *args)
        ev = self.attr2ev(attr)
        return sender

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []
