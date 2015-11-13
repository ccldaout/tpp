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
_ATTR_CIDARG = '_RPC_CIDARG'

class _ProxyFrontend(object):
    __slots__ = ['_proxy_id', '_port', '__name__', '__doc__']
    _lock = tu.Lock()
    _reply_id = 0
    _mbox = tb.OnetimeMsgBox()

    def __new__(cls, port, proxy_backend_id):
        self = super(_ProxyFrontend, cls).__new__(cls)
        self._port = port
        self._proxy_id = proxy_backend_id
        return self

    def __call__(self, *args, **kwargs):
        with self._lock:
            type(self)._reply_id += 1
            reply_id = self._reply_id
        port = self._port
        msg = ['call', reply_id, self._proxy_id, args, kwargs]
        msg = _ProxyBackendManager.convert(port, msg)
        if port.mainthread is tu.current_thread():
            port.send(msg)
            msg = port.main_loop(lambda m: m[0] == 'reply' and m[1] == reply_id)
        else:
            self._mbox.reserve(reply_id)
            port.send(msg)
            msg = self._mbox.wait(reply_id)
        if msg[2]:
            return _ProxyBackendManager.convert(port, msg[3])
        else:
            raise msg[3]

    @classmethod
    def reply(cls, msg):
        # msg: ['reply', reply_id, True/False, value/exception]
        cls._mbox.post(msg[1], msg)

    def __del__(self):
        ___(self._port.send)(['unref', self._proxy_id])
        if hasattr(super(_ProxyFrontend, self), '__del__'):
            super(_ProxyFrontend, self).__del__()

class _ProxyPackage(object):
    __slots__ = ['proxy_id']

    def __new__(cls, proxy_backend_id = None):
        self = super(_ProxyPackage, cls).__new__(cls)
        self.proxy_id = proxy_backend_id
        return self

    def __repr__(self):
        return '<_ProxyPackage:%d>' % self.proxy_id

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
            if callable(v):
                return _ProxyPackage(cls._register(v))
            if isinstance(v, _ProxyPackage):
                return _ProxyFrontend(port, v.proxy_id)
            if isinstance(v, dict):
                v = dict([(k, _convert(e)) for k, e in v.items()])
            elif isinstance(v, (list, tuple)):
                v = [_convert(e) for e in v]
            return v
        return _convert(msg)

    @classmethod
    def call(cls, port, reply_id, proxy_id, args, kwargs):
        try:
            with cls._lock:
                f = cls._proxy_db[proxy_id]
            args = cls.convert(port, args)
            kwargs = cls.convert(port, kwargs)
            if hasattr(f, _ATTR_CIDARG):
                ret = f(port.order, *args, **kwargs)
            else:
                ret = f(*args, **kwargs)
            port.send(['reply', reply_id, True, cls.convert(port, ret)])
        except Exception as e:
            port.send(['reply', reply_id, False, e])

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

class RpcServer(_RpcCommon):
    def __new__(cls, *args, **kwargs):
        self = super(RpcServer, cls).__new__(cls)
        self._exports = []		# list of (frontend, name, doc)
        self._cb_accepted = tb.Delegate()
        self._cb_disconnected = tb.Delegate()
        self._cids = set([])
        return self

    @classmethod
    def export(cls, arg=None):
        def _export(func):
            if isinstance(arg, str):
                func.__name__ = arg
            setattr(func, _ATTR_EXPORT, True)
            vars = func.__code__.co_varnames
            if 'cid__' in vars and vars.index('cid__') == 1:
                setattr(func, _ATTR_CIDARG, True)
            return func
        if callable(arg):
            return _export(arg)
        else:
            return _export

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
    def __new__(cls, *args, **kwargs):
        self = super(_RpcClient, cls).__new__(cls)
        self._proxy = None
        self._proxy_cond = tu.Condition()
        self._port = None
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
                self._proxy_cond.wait()
            return self._proxy

#----------------------------------------------------------------------------
#                           Convenient interface
#----------------------------------------------------------------------------

export = RpcServer.export

def server(addr, funcs_list, background=True):
    svc = RpcServer()
    for funcs in funcs_list:
        svc.exports(funcs)
    ipc.Acceptor(svc, addr).start(background)

class client(object):
    def __new__(cls, addr):
        self = super(client, cls).__new__(cls)
        self._rc = _RpcClient()
        ipc.Connector(self._rc, addr).start()
        return self
    
    def __getattr__(self, name):
        return getattr(self._rc.proxy, name)

    def __del__(self):
        self._rc.stop()
        self._rc = None
        if hasattr(super(client, self), '__del__'):
            super(client, self).__del__()

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []

if __name__ == '__main__':
    pass
