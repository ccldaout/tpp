from tpp import threadutil as tu
from tpp import rpc
import threading
import time

addr = ('localhost', 55222)

class Service(object):
    @rpc.export
    def register(self, callback):
        self.cnt = 0
        self.callback = callback
        t = tu.Thread(target=self.lazy)
        t.daemon = True
        t.start()

    def lazy(self):
        time.sleep(5)
        self.cnt = self.callback(self.cnt)
        tu.pr('lazy: new cnt: %d', self.cnt)
        t = tu.Thread(target=self.lazy)
        t.daemon = True
        t.start()

def server():
    rpc.server(addr, [Service()])

api = None
def client():
    def callback(cnt):
        tu.pr('callback: %s', cnt)
        return cnt+1
    global api
    api = rpc.client(addr)
    api.register(callback)

print
print "server() / client()"
print
