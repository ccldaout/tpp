from tpp import threadutil as tu
from tpp import rpc
import threading
import time

tu.pr.print_name = True

addr0 = ('localhost', 55222)
addr1 = ('localhost', 55223)

class Serv0(object):
    @rpc.export
    def call(self, func, *args, **kwargs):
        tu.pr('Serv0.call ...')
        func(*args, **kwargs)
        tu.pr('Serv0.call ... end')

class Serv1(object):
    def __init__(self):
        self._rpc = rpc.client(addr0)

    @rpc.export
    def save(self, callback):
        self._callback = callback

    @rpc.export
    def get(self):
        return self._callback

    @rpc.export
    def call(self, *args, **kwargs):
        tu.pr('Serv1.call ...')
        self._callback(*args, **kwargs)
        tu.pr('Serv1.call ... end')

    @rpc.export
    def call2(self, *args, **kwargs):
        tu.pr('Serv1.call2 ...')
        self._rpc.call(self._callback, *args, **kwargs)
        tu.pr('Serv1.call2 ... end')

def serv0():
    rpc.server(addr0, [Serv0()])

def serv1():
    rpc.server(addr1, [Serv1()])

api = None
def client():
    def callback(cnt):
        tu.pr('callback: %s', cnt)
        return '*'*cnt
    global api
    api = rpc.client(addr1)
    api.save(callback)

print
print "serv0() / serv1() / client()"
print
