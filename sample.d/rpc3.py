from tpp import threadutil as tu
from tpp import rpc
import threading
import time

tu.pr.print_name = True

addr = ('localhost', 55222)

class Server(object):
    @rpc.export
    def call(self, itv_s, n, callback):
        for i in xrange(n):
            time.sleep(itv_s)
            tu.pr('callback ...')
            callback(i)
            tu.pr('callback end')
        return n

def server():
    rpc.server(addr, [Server()])

api = None
def client():
    def cb1(cnt):
        tu.pr('cb1: %s', cnt)
        time.sleep(2)
        return '*'*cnt
    def cb2(cnt):
        tu.pr('cb2: %s', cnt)
        time.sleep(1.5)
        return '*'*cnt
    global api
    api = rpc.client(addr)
    tu.threadpool.queue(api.call, 0.5, 10, cb1)
    tu.threadpool.queue(api.call, 0.6, 7, cb2)

print
print "server() / client()"
print
