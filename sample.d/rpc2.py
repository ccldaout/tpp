from tpp import threadutil as tu
from tpp import rpc
import threading
import traceback

addr = ('localhost', 55222)

class Service(object):
    def __init__(self):
        self._users = {}

    def on_connection(self, cid__):
        self._users[cid__] = ('*no name*', None)

    def on_disconnection(self, cid__):
        name, _ = self._users[cid__]
        del self._users[cid__]
        self.notify_all('*server*', 'exit: %s' % name)

    def notify_all(self, sender_name, msg):
        for n, rcv in self._users.values():
            try:
                if rcv:
                    rcv(sender_name, msg)
            except:
                traceback.print_exc()

    @rpc.export
    def greet(self, cid__, name, receiver):
        '''greet(name, receiver)'''
        self._users[cid__] = (name, receiver)
        tu.pr('greet: cid__(%s) -> %s', cid__, name)
        self.notify_all('*server*', 'enter: %s' % name)

    @rpc.export
    def list(self):
        '''list() -> [name, ...]'''
        return [n for n, _ in self._users.values()]

    @rpc.export
    def say(self, cid__, msg):
        '''say(msg)'''
        name, _ = self._users[cid__]
        self.notify_all(name, msg)

def server():
    rpc.server(addr, [Service()])

api = None
def client(name):
    def receiver(sender_name, msg):
        tu.pr("RECEIVE: %s -> '%s'", sender_name, msg)
    global api
    api = rpc.client(addr)
    api.greet(name, receiver)

print
print "server() / client(name)"
print
