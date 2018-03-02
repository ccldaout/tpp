# -*- coding: utf-8 -*-

import socket
import struct
import sys


#----------------------------------------------------------------------------
#                        machine dependent functions
#----------------------------------------------------------------------------

#### thread
import thread as _thread

def _thread_start(func, args, **kwargs):
    return _thread.start_new_thread(func, args)

def _thread_getlock():
    return _thread.allocate_lock()

#### poll
from tpp import mpoll

#### socket.read
def _recvall(sock, n):
    s = ''
    while n:
        s2 = sock.recv(n)
        if not s2:
            break
        s += s2
        n -= len(s2)
    return s
        
#### print exception
import traceback
def _print_exception(e):
    traceback.print_exc()


#----------------------------------------------------------------------------
#
#----------------------------------------------------------------------------

class PortError(Exception):
    pass

class SocketClosed(PortError):
    pass

class SocketUnexpectedClosed(PortError):
    pass

class SocketIOError(PortError):
    pass

class ProtocolError(PortError):
    pass

class RemoteHandlerError(PortError):
    pass

class PackerBase(object):
    def pack(self, msg):
        raise NotImplementedError()
    def unpack(self, sock):
        raise NotImplementedError()
    def __call__(self):
        return self

class DumpPackerBase(PackerBase):
    @staticmethod
    def dumps(msg):
        raise NotImplementedError()

    @staticmethod
    def loads(data):
        raise NotImplementedError()

    def pack(self, msg):
        data = self.dumps(msg)
        n = len(data)
        return struct.pack('<i', n)+data, n+4

    def unpack(self, sock):
        size_str = _recvall(sock, 4)
        if not size_str:
            raise SocketClosed()
        if len(size_str) != 4:
            raise SocketUnexpectedClosed()
        n, = struct.unpack('<i', size_str)
        data = _recvall(sock, n)
        if len(data) != n:
            raise SocketUnexpectedClosed()
        return self.loads(data)

class JSONPacker(DumpPackerBase):
    import json
    dumps = staticmethod(json.dumps)
    loads = staticmethod(json.loads)

class PyPacker(DumpPackerBase):
    import cPickle
    dumps = staticmethod(lambda msg: cPickle.dumps(msg, cPickle.HIGHEST_PROTOCOL))
    loads = staticmethod(cPickle.loads)

class UDPDumpPackerBase(DumpPackerBase):

    MAXLEN = 512
    recv_addr = None

    def pack(self, msg):
        data = self.dumps(msg)
        n = len(data)
        if n > self.MAXLEN:
            raise PortError('UDP data size is too large.')
        return data, n

    def unpack(self, sock):
        data, addr = sock.recvfrom(self.MAXLEN)
        self.recv_addr = addr
        return self.loads(data)

class UDPJSONPacker(UDPDumpPackerBase):
    import json
    dumps = staticmethod(json.dumps)
    loads = staticmethod(json.loads)


#----------------------------------------------------------------------------
#
#----------------------------------------------------------------------------

class IOPort(object):
    acceptable = False

    def __init__(self, sock=None, packer=None):
        if packer is None:
            packer = JSONPacker()
        if sock:
            self.socket = sock
        self._packer = packer
        self._lock = _thread_getlock()
        self._event = None
        self._autoreply_names = set()
        if isinstance(packer, UDPDumpPackerBase):
            self.send = self._send_udp

    def connect(self, addr):
        sock = socket.socket()
        sock.connect(addr)
        self.socket = sock
        return self				# for method chain

    def negotiate(self):
        self._autoreply_names = set(self.send(['mipc_negotiate']).result())
        return self				# for method chain

    def recv(self):
        return self._packer.unpack(self.socket)

    def send(self, msg):
        self._event = msg[0]
        data, n = self._packer.pack(msg)
        with self._lock:
            self.socket.sendall(data)		# raise exception if error
        return self

    def _send_udp(self, msg):
        self._event = msg[0]
        data, n = self._packer.pack(msg)
        with self._lock:
            addr = self._packer.recv_addr
            if addr:
                self.socket.sendto(data, addr)
            else:
                self.socket.send(data)
        return self

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def result(self):
        ev, status, value = self.recv()
        expect = self._event + '_reply'
        if ev != expect:
            raise ProtocolError('%s is expected, but %s is received.' % (expect, ev))
        if status:
            return value
        raise RemoteHandlerError('Exception happen on remote:\n' + value)

    def __getattr__(self, name):
        def _send(*args):
            msg = [name]
            msg.extend(args)
            self.send(msg)
            if name in self._autoreply_names:
                return self.result()
            return self		# for method chain
        return _send

def client(addr, packer=None):
    return IOPort(packer=packer).connect(addr).negotiate()

def udp_client(addr, packer=None):
    if packer is None:
        packer = UDPJSONPacker()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(addr)
    sock.settimeout(5.0)	# TODO
    return IOPort(sock=sock, packer=packer).negotiate()

def udp_server(addr, packer=None):
    if isinstance(addr, int):
        addr = ('0.0.0.0', addr)
    if packer is None:
        packer = UDPJSONPacker()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(addr)
    sock.settimeout(5.0)	# TODO
    return IOPort(sock=sock, packer=packer)

class AcceptablePort(object):
    acceptable = True

    def __init__(self, sock_addr, packer=None):
        self.socket = socket.socket()
        self.socket.bind(sock_addr)
        self.socket.listen(1)
        self._packer = packer

    def accept(self):
        iosocket, _ = self.socket.accept()
        packer = self._packer
        return IOPort(sock=iosocket,
                      packer=(packer() if packer else None))

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

class _AutoReply(object):
    def __init__(self):
        self._autoreply_names = set()

    def __contains__(self, item):
        return item in self._autoreply

    def decorator_autoreply(self, target):
        if isinstance(target, type):
            self._autoreply_names.update(target._autoreply_names)
            target._autoreply_names = self._autoreply_names
            self._autoreply_names = set()
            return target
        else:
            def wrapper(svc_self, port, msg):	# args: self, port, msg
                reply = msg[0] + '_reply'
                try:
                    ret = target(svc_self, *msg[1:])
                    port.send([reply, True, ret])
                except Exception as e:
                    port.send([reply, False, str(e)])
                    _print_exception(e)
            wrapper.__name__ = target.__name__
            self._autoreply_names.add(target.__name__)
            return wrapper

    def decorator_noreply(self, target):
        def wrapper(svc_self, port, msg):	# args: self, port, msg
            ret = target(svc_self, *msg[1:])
        return wrapper
    
_AutoReply = _AutoReply()
autoreply =_AutoReply.decorator_autoreply
noreply = _AutoReply.decorator_noreply

class _ServiceMeta(type):
    def __new__(mcls, name, bases, dic):
        cls = super(_ServiceMeta, mcls).__new__(mcls, name, bases, dic)
        cls = autoreply(cls)
        return cls

class ServiceBase(object):
    __metaclass__ = _ServiceMeta

    _autoreply_names = set()

    def __call__(self, port):
        return self

    # mipc_ prefixed methods are reserved for internal.

    def mipc_negotiate(self, port, msg):
        port.send(['mipc_negotiate_reply', True, list(self._autoreply_names)])

    def mipc_received(self, port, msg):
        name = msg[0]
        if hasattr(self, name):
            getattr(self, name)(port, msg)
        else:
            self.on_default(port, msg)

    # on_ prefixed methods are overridable.

    def on_default(self, port, msg):
        raise NotImplementedError(msg[0])

    def on_accepted(self, port):
        pass

    def on_disconnected(self, port):
        pass

    def on_exception(self, port):
        pass

class _ServiceManager(object):
    def __init__(self):
        self._poll = mpoll.poll()
        self._ports = {}
        self.ip_address = '0.0.0.0'
        _thread_start(self.loop, ())

    def register_server(self, addr, service_object, packer=None):
        if isinstance(addr, int):
            addr = (self.ip_address, addr)
        port = AcceptablePort(addr, packer=packer)
        self.register(port, service_object)

    def register(self, port, service_object):
        fd = port.socket.fileno()
        self._poll.register(port.socket, mpoll.POLLIN)
        self._ports[fd] = (port, service_object)

    def unregister(self, port):
        fd = port.socket.fileno()
        self._poll.unregister(port.socket)
        if fd in self._ports:
            del self._ports[fd]

    def loop(self):
        while True:
            for fobj, flag in self._poll.ipoll():
                fd = fobj.fileno()
                port, service_object = self._ports[fd]
                if port.acceptable:
                    newport = None
                    try:
                        newport = port.accept()
                        service_object = service_object(port)
                        self.register(newport, service_object)
                        service_object.on_accepted(newport)
                    except Exception as e:
                        _print_exception(e)
                        if newport:
                            self.unregister(newport)
                            newport.close()
                else:
                    try:
                        msg = port.recv()
                        service_object.mipc_received(port, msg)
                    except SocketClosed as e:
                        self.unregister(port)
                        service_object.on_disconnected(port)
                        port.close()
                    except Exception as e:
                        _print_exception(e)
                        self.unregister(port)
                        service_object.on_exception(port)
                        port.close()

manager = _ServiceManager()
