# -*- coding: utf-8 -*-

import cPickle
import os
import select
import socket
import struct
import sys
import time
import traceback
import tpp.threadutil as tu
import tpp.toolbox as tb

___ = tb.no_except

#----------------------------------------------------------------------------
#                          simple socket wrappter
#----------------------------------------------------------------------------

class CSocket(object):

    def __getattr__(self, attr):
        return getattr(self._sock, attr)
    
    def __new__(cls, addr, server=False, backlog=2):
        self = super(CSocket, cls).__new__(cls)
        self.send_tmo_s = 120
        self.init_recv_tmo_s = None
        self.next_recv_tmo_s = 120
        self.is_server = server
        if isinstance(addr, socket.socket):
            self._sock = addr
            self.tcpnodelay()
            self.tcpkeepalive()
            return self
        af = socket.AF_UNIX
        if isinstance(addr, tuple):
            af = socket.AF_INET
        elif ':' in addr:
            host, port = addr.split(':')
            if port.isdigit():
                if host == '*':
                    host = ''
                addr = (host, int(port))
                af = socket.AF_INET
        self._sock = socket.socket(af)
        try:
            if server:
                if af == socket.AF_UNIX:
                    ___(os.unlink)(addr)
                self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.bind(addr)
                self.listen(backlog)
            else:
                self.tcpnodelay()
                self.tcpkeepalive()
                self.connect(addr)
        except:
            self.close()
            raise
        return self

    def close(self, *args):
        ___(self._sock.close)(*args)

    def accept(self, *args):
        s, addr = self._sock.accept(*args)
        ns = type(self)(s)
        ns.send_tmo_s = self.send_tmo_s
        ns.init_recv_tmo_s = self.init_recv_tmo_s
        ns.next_recv_tmo_s = self.next_recv_tmo_s
        ns.is_server = True
        return (ns, addr)

    def setsockopt(self, *args):
        return ___(self._sock.setsockopt)(*args)

    def tcpnodelay(self, setting=1):
        self.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, setting)

    def tcpkeepalive(self, kpidle=180, kpintvl=5, kpcnt=12):
        try:
            avail = int(kpidle > 0)
            self.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, avail)
            if avail == 0:
                return
            for kpopt, kpval in [('ALIVE', kpidle), ('IDLE', kpidle),
                                 ('INTVL', kpintvl), ('CNT', kpcnt)]:
                kpopt = 'TCP_KEEP' + kpopt
                if hasattr(socket, kpopt):
                    self.setsockopt(socket.IPPROTO_TCP, getattr(socket, kpopt), kpval)
        except:
            pass

    def wait_readable(self, tmo_s=None):
        rok, _, _ = select.select([self._sock], [], [], tmo_s)
        return bool(rok)

    def wait_writable(self, tmo_s=None):
        _, wok, _ = select.select([], [self._sock], [], tmo_s)
        return bool(wok)

    def recv_x(self, size):
        # return: (data, rest_size)
        # exception: socket.timeout, socket.error
        data = ''
        tmo_s = self.init_recv_tmo_s
        while size > 0:
            if (tmo_s is not None) and (not self.wait_readable(tmo_s)):
                raise socket.timeout('recv timeout: %f' % tmo_s)
            s = self._sock.recv(size)
            if not s:
                return data, size
            size -= len(s)
            data += s
            tmo_s = self.next_recv_tmo_s
        return data, 0

    def send_x(self, buf, size=None):
        # exception: socket.timeout, socket.error
        if size is None:
            size = len(buf)
        buf = memoryview(buf)[:size]
        tmo_s = self.send_tmo_s
        while size > 0:
            if (tmo_s is not None) and (not self.wait_writable(tmo_s)):
                raise socket.timeout('send timeout: %f' % tmo_s)
            n = self._sock.send(buf)
            size -= n
            buf = buf[n:]
            tmo_s = self.send_tmo_s

    def shutdown(self, write=False, read=False):
        if write and read:
            m = socket.SHUT_RDWR
        elif write:
            m = socket.SHUT_WR
        else:
            m = socket.SHUT_RD
        try:
            self._sock.shutdown(m)
        except:
            traceback.print_exc()

#----------------------------------------------------------------------------
#                           Simple IPC framework
#----------------------------------------------------------------------------

class NoMoreData(Exception):
    pass

class PackerMeta(type):
    def __new__(mcls, name, bases, dic):
        if os.getenv('TPP_IPC_DEBUG'):
            def wrapper_pack(f):
                def pack(self, msg):
                    tu.pr('  PACK: %s', msg)
                    return f(self, msg)
                return pack
            def wrapper_unpack(f):
                def unpack(self, csock):
                    msg = f(self, csock)
                    tu.pr('UNPACK: %s', msg)
                    return msg
                return unpack
            dic['pack'] = wrapper_pack(dic['pack'])
            dic['unpack'] = wrapper_unpack(dic['unpack'])
        cls = super(PackerMeta, mcls).__new__(mcls, name, bases, dic)
        return cls

class PackerBase(object):
    __metaclass__ = PackerMeta

    def pack(self, msg):
        raise NotImplementedError('pack')
        
    def unpack(self, csock):
        raise NotImplementedError('unpack')

class PyPacker(PackerBase):
    MAX_PICKLED = (1024*1024*16)

    def pack(self, msg):
        s = cPickle.dumps(msg, cPickle.HIGHEST_PROTOCOL)
        n = len(s)
        return struct.pack('<i', n)+s, n+4
        
    def unpack(self, csock):
        s, n = csock.recv_x(4)
        if not s:
            raise NoMoreData('Peer maybe finish sending data')
        if n != 0:
            raise EOFError('Unexpeceted disconnection (error)')
        n, = struct.unpack('<i', s)
        if not (0 < n <= self.MAX_PICKLED):
            raise RuntimeError('Pickled object size is too large: %d' % n)
        s, n = csock.recv_x(n)
        if n != 0:
            raise EOFError('Unexpected disconnection (error)')
        return cPickle.loads(s)

class ServiceBase(object):
    def __new__(cls, *args, **kwargs):
        self = super(ServiceBase, cls).__new__(cls)
        self.__ports = []
        return self

    def __call__(self):
        return self

    def link(self, port):
        if port not in self.__ports:
            self.__ports.append(port)

    def unlink(self, port):
        if port in self.__ports:
            self.__ports.remove(port)

    def sendall(self, msg):
        for p in self.__ports[:]:
            p.send(msg)

    def handle(self, port, msg):
        fn = 'handle_' + str(msg[0])
        if hasattr(self, fn):
            getattr(self, fn)(port, msg)
        else:
            self.handle_default(port, msg)

    def handle_default(self, port, msg):
        raise NotImplementedError('handle_%s' % str(msg[0]))

    def handle_CONNECTED(self, port):
        pass

    def handle_ACCEPTED(self, port):
        pass

    def handle_DISCONNECTED(self, port):
        pass

    def handle_SOCKERROR(self, port):
        pass

class IPCPort(object):
    _counter = tb.Counter()

    def __new__(cls, service_object, packer, csock):
        self = super(IPCPort, cls).__new__(cls)
        self._service = service_object
        self._packer = packer if packer else PyPacker()
        self._csock = csock
        self._send_queue = tu.Queue()
        self._send_error = None
        self.mainthread = None
        self.order = self._counter()
        return self

    def __repr__(self):
        return '<IPCPort#%d>' % self.order

    def _send_loop(self):
        while True:
            msg = self._send_queue.get()
            if msg is False:
                return
            try:
                s, n = self._packer.pack(msg)
                self._csock.send_x(s, n)
            except Exception as e:
                traceback.print_exc()
                self._send_error = (e, msg)
                self._csock.shutdown(read=True)
                return

    def _send_thread(self):
        try:
            self._send_loop()
        except:
            pass
        self._service.unlink(self)
        self._csock.shutdown(write=True)
        ___(self._send_queue.stop)(soon=True)

    def main_loop(self, return_condition):
        while True:
            try:
                msg = self._packer.unpack(self._csock)
                self._service.handle(self, msg)
                if return_condition(msg):
                    return msg
            except Exception as e:
                if self._send_error:
                    e, msg = self._send_error
                    e.args = (e.args[0] + '\n' + str(msg)[:70],) + e.args[1:]
                if isinstance(e, NoMoreData):
                    self._service.handle_DISCONNECTED(self)
                else:
                    traceback.print_exception(type(e), e, sys.exc_traceback)
                    self._service.handle_SOCKERROR(self)
                return e

    def _main_thread(self, send_thread, fin_func):
        try:
            if self._csock.is_server:
                self._service.link(self)
                self._service.handle_ACCEPTED(self)
            else:
                self._service.handle_CONNECTED(self)
            self.main_loop(lambda m:False)
        except:
            traceback.print_exc()
        ___(self._send_queue.stop)(soon=False)
        send_thread.join()
        self._service = None
        self.mainthread = None
        self._csock.close()
        if fin_func:
            fin_func()

    def start(self, fin_func=None):
        t = tu.Thread(target=self._send_thread)
        t.daemon = True
        t.name = 'port.sender'
        t.start()

        t = tu.Thread(target=self._main_thread, args=(t, fin_func))
        t.daemon = True
        t.name = 'port.main'
        self.mainthread = t
        t.start()

    def send(self, msg):
        self._send_queue.put(msg)

    def send_fin(self, soon=False):
        ___(self._send_queue.stop)(soon)

class Connector(object):
    def __new__(cls, service_object, addr, recover=False, packer=None):
        self = super(Connector, cls).__new__(cls)
        self._service = service_object
        self._packer = packer
        self._addr = addr
        self._recover = recover
        self._retry_itv_s = 5
        self._retry_exc_n = 60 / self._retry_itv_s
        return self

    def _main_thread(self):
        retry = 0
        fin_func = self.start if self._recover else None
        while True:
            csock = None
            try:
                csock = CSocket(self._addr) 
                self._port = IPCPort(self._service, self._packer, csock)
                self._port.start(fin_func)
                return
            except:
                if retry % self._retry_exc_n == 0:
                    traceback.print_exc()
                if csock:
                    csock.close()
                time.sleep(self._retry_itv_s)
                retry += 1

    def start(self):
        self._thread = tu.Thread(target=self._main_thread)
        self._thread.daemon = True
        self._thread.name = 'connector'
        self._thread.start()
        return self
    
    @property
    def port(self):
        self._thread.join()
        return self._port

class Acceptor(object):
    def __new__(cls, service_factory, addr, packer=None):
        self = super(Acceptor, cls).__new__(cls)
        self._service_factory = service_factory
        self._packer = packer
        self._addr = addr
        return self

    def _main_thread(self, svr_csock):
        while True:
            csock, _ = svr_csock.accept()
            try:
                IPCPort(self._service_factory(), self._packer, csock).start()
            except:
                traceback.print_exc()
                csock.close()

    def start(self, background=True):
        svr_csock = CSocket(self._addr, server=True)
        if background:
            t = tu.Thread(target=self._main_thread, args=(svr_csock,))
            t.daemon = True
            t.name = 'acceptor'
            t.start()
        else:
            self._main_thread(svr_csock)

#----------------------------------------------------------------------------
#                   Simple client object (no event loop)
#----------------------------------------------------------------------------

class SimpleClient(object):
    def __new__(cls, addr, packer=None):
        self = super(SimpleClient, cls).__new__(cls)
        self._addr = addr
        self._packer = packer if packer else PyPacker()
        return self

    def start(self):
        self._csock = CSocket(self._addr) 

    def recv(self):
        return self._packer.unpack(self._csock)
        
    def send(self, msg):
        s, n = self._packer.pack(msg)
        self._csock.send_x(s, n)
        
    def send_fin(self):
        self._csock.shutdown(write=True)
        
    def close(self):
        self._csock.close()

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []

if __name__ == '__main__':
    pass
