# -*- coding: utf-8 -*-

import inspect
from tpp import ipc
from tpp import toolbox as tb
from tpp import threadutil as tu

___ = tb.no_except

#----------------------------------------------------------------------------
#                            RPC main framework
#----------------------------------------------------------------------------

_ATTR_EXPORT = '_RPC_EXPORT'
_ATTR_QUICK  = '_RPC_QUICK'
_ATTR_CIDARG = '_RPC_CIDARG'
_ATTR_NOREPL = '_RPC_NOREPL'

class _ProxyFrontend(object):
    __slots__ = ['_proxy_id', '_port', '_no_reply', '__name__', '__doc__']
    _mbox = tb.OnetimeMsgBox()

    def __new__(cls, port, proxy_backend_id, no_reply):
        self = super(_ProxyFrontend, cls).__new__(cls)
        self._port = port
        self._proxy_id = proxy_backend_id
        self._no_reply = no_reply
        return self

    def __call__(self, *args, **kwargs):
        port = self._port
        if self._no_reply:
            reply_id = 0
        else:
            reply_id = self._mbox.reserve()
        msg = ['call', reply_id, self._proxy_id, args, kwargs]
        msg = _ProxyBackendManager.convert(port, msg)
        port.send(msg)
        if self._no_reply:
            return
        msg = self._mbox.wait(reply_id)
        if msg[2]:
            return _ProxyBackendManager.convert(port, msg[3])
        else:
            raise msg[3]

    def convert(self, port):
        if self._port == port:
            return _ProxyPackage(-self._proxy_id, self._no_reply)
        else:
            return _ProxyPackage(_ProxyBackendManager._register(self), self._no_reply)

    @classmethod
    def reply(cls, msg):
        # msg: ['reply', reply_id, True/False, value/exception]
        cls._mbox.post(msg[1], msg)

    def __del__(self):
        # [AD-HOC] try..except is to suppress error whene interpeter shutdown
        try:
            self._port.send(['unref', self._proxy_id])
        except:
            pass

class _ProxyPackage(object):
    __slots__ = ['proxy_id', 'no_reply']

    def __new__(cls, proxy_backend_id=None, no_reply=False):
        self = super(_ProxyPackage, cls).__new__(cls)
        self.proxy_id = proxy_backend_id
        self.no_reply = no_reply
        return self

    def __repr__(self):
        return '<_ProxyPackage:%d>' % self.proxy_id

    def convert(self, port):
        if self.proxy_id > 0:
            return _ProxyFrontend(port, self.proxy_id, self.no_reply)
        else:
            return _ProxyBackendManager.get(-self.proxy_id)

class _ProxyBackendManager(object):
    _lock = tu.Lock()
    _proxy_id = 0
    _proxy_db = {}

    @classmethod
    def _register(cls, func):
        with cls._lock:
            cls._proxy_id += 1
            cls._proxy_db[cls._proxy_id] = func
            return cls._proxy_id

    @classmethod
    def convert(cls, port, msg):
        def _convert(v):
            if inspect.isbuiltin(v) or inspect.isclass(v):
                return v
            if isinstance(v, (_ProxyPackage, _ProxyFrontend)):
                return v.convert(port)
            if callable(v):
                return _ProxyPackage(cls._register(v), hasattr(v, _ATTR_NOREPL))
            if isinstance(v, dict):
                v = dict([(k, _convert(e)) for k, e in v.items()])
            elif isinstance(v, (list, tuple)):
                v = [_convert(e) for e in v]
            return v
        return _convert(msg)

    @classmethod
    def _call(cls, port, reply_id, func, args, kwargs):
        try:
            args = cls.convert(port, args)
            kwargs = cls.convert(port, kwargs)
            if hasattr(func, _ATTR_CIDARG):
                ret = func(port.order, *args, **kwargs)
            else:
                ret = func(*args, **kwargs)
            if reply_id:
                port.send(['reply', reply_id, True, cls.convert(port, ret)])
        except Exception as e:
            if reply_id:
                port.send(['reply', reply_id, False, e])

    @classmethod
    def call(cls, port, reply_id, proxy_id, args, kwargs):
        try:
            with cls._lock:
                func = cls._proxy_db[proxy_id]
            if hasattr(func, _ATTR_QUICK):
                cls._call(port, reply_id, func, args, kwargs)
            else:
                tu.threadpool.queue(cls._call, port, reply_id, func, args, kwargs)
        except Exception as e:
            if reply_id:
                port.send(['reply', reply_id, False, e])

    @classmethod
    def get(cls, proxy_id):
        with cls._lock:
            return cls._proxy_db[proxy_id]

    @classmethod
    def unref(cls, proxy_id):
        with cls._lock:
            cls._proxy_db.pop(proxy_id, None)

class _RpcCommon(ipc.ServiceBase):
    def handle_call(self, port, msg):
        # msg: ['call', reply_id, proxy_id, args, kwargs]
        _ProxyBackendManager.call(port, *msg[1:])

    def handle_reply(self, port, msg):
        # msg: ['reply', reply_id, True/False, value/exception]
        _ProxyFrontend.reply(msg)

    def handle_unref(self, port, msg):
        # msg: ['unref', proxy_id]
        _ProxyBackendManager.unref(msg[1])

    def handle_DISCONNECTED(self, port):
        pass

    def handle_SOCKERROR(self, port):
        pass

class _RpcServer(_RpcCommon):
    def __new__(cls, *args, **kwargs):
        self = super(_RpcServer, cls).__new__(cls)
        self._exports = []		# list of (frontend, name, doc)
        self._cb_accepted = tb.Delegate()
        self._cb_disconnected = tb.Delegate()
        self._cids = set([])
        return self

    @classmethod
    def export(cls, f=None, **kwargs):
        def _export(func):
            v = kwargs.pop('name', None)
            if v:
                func.__name__ = v
            v = kwargs.pop('quick', False)
            if v:
                setattr(func, _ATTR_QUICK, True)
            v = kwargs.pop('no_reply', False)
            if v:
                setattr(func, _ATTR_NOREPL, True)
            if kwargs:
                raise TypeError('unknown keyword arguments: %s' % kwargs)
            setattr(func, _ATTR_EXPORT, True)
            vars = func.__code__.co_varnames
            if 'cid__' in vars and vars.index('cid__') == 1:
                setattr(func, _ATTR_CIDARG, True)
            return func
        if callable(f) and not kwargs:
            return _export(f)
        elif f is None and kwargs:
            return _export
        else:
            raise TypeError('Invalid usage of @rpc.export')

    def exports(self, rpcitf):
        cnv = lambda v:_ProxyBackendManager.convert(None, v)
        for k, v in inspect.getmembers(rpcitf):
            if k[0] != '_' and callable(v) and hasattr(v, _ATTR_EXPORT):
                self._exports.append((cnv(v), v.__name__, v.__doc__))
        if hasattr(rpcitf, 'handle_ACCEPTED'):
            self._cb_accepted += rpcitf.handle_ACCEPTED
        if hasattr(rpcitf, 'handle_DISCONNECTED'):
            self._cb_disconnected += rpcitf.handle_DISCONNECTED
        return self

    def handle_ACCEPTED(self, port):
        port.send(['register', self._exports])
        self._cids.add(port.order)
        self._cb_accepted(port.order)

    def handle_DISCONNECTED(self, port):
        if port.order in self._cids:
            self._cids.remove(port.order)
            self._cb_disconnected(port.order)

    def handle_SOCKERROR(self, port):
        return self.handle_DISCONNECTED(port)

class _RpcClient(_RpcCommon):
    def __new__(cls, itmo_s, *args, **kwargs):
        self = super(_RpcClient, cls).__new__(cls)
        self._proxy = None
        self._proxy_cond = tu.Condition()
        self._port = None
        self._itmo_s = itmo_s
        return self

    def _create_proxy(self, frontend, name, doc):
        def _proxy_function(*args, **kwargs):
            return frontend(*args, **kwargs)
        _proxy_function.__name__ = name
        _proxy_function.__doc__ = doc
        return _proxy_function

    def handle_register(self, port, msg):
        # msg: ['register', [(func, name, doc) ...]]
        self._port = port
        class Proxies(object):
            pass
        proxy = Proxies()
        for f, n, d in _ProxyBackendManager.convert(port, msg[1]):
            setattr(proxy, n, self._create_proxy(f, n, d))
        with self._proxy_cond:
            self._proxy = proxy
            self._proxy_cond.notify_all()

    def stop(self):
        if self._port:
            self._port.send_fin()
            self._port = None
        with self._proxy_cond:
            self._proxy = None

    @property
    def proxy(self):
        with self._proxy_cond:
            while self._proxy is None:
                if not self._proxy_cond.wait(self._itmo_s):
                    return None
            return self._proxy

#----------------------------------------------------------------------------
#                           Convenient interface
#----------------------------------------------------------------------------

export = _RpcServer.export

def server(addr, funcs_list, background=True, thread_max=0, thread_lwm=0):
    if tu.threadpool.thread_max < thread_max:
        tu.threadpool.thread_max = thread_max
    if tu.threadpool.thread_lwm < thread_lwm:
        tu.threadpool.thread_lwm = thread_lwm
    svc = _RpcServer()
    for funcs in funcs_list:
        svc.exports(funcs)
    ipc.Acceptor(svc, addr).start(background)

class client(object):
    def __new__(cls, addr,
                itmo_s=2.0, ctmo_s=None, background=True, lazy_setup=True):
        self = super(client, cls).__new__(cls)
        self._prm = (addr, itmo_s, ctmo_s, background)
        self._lock = tu.RLock()
        if not lazy_setup:
            self._setup()
        return self
    
    def _setup(self):
        addr, itmo_s, ctmo_s, bg = self._prm
        self._rc = _RpcClient(itmo_s=itmo_s)
        ipc.Connector(self._rc, addr, retry=False, ctmo_s=ctmo_s).start(background=bg)

    def __getattr__(self, name):
        with self._lock:
            if name == '_rc':
                self._setup()
                return self._rc
            v = getattr(self._rc.proxy, name)
            self.__dict__[name] = v
            return v

    def __del__(self):
        # [AD-HOC] try..except is to suppress error whene interpeter shutdown
        try:
            if self._rc:
                self._rc.stop()
                self._rc = None
        except:
            pass

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []

if __name__ == '__main__':
    pass
