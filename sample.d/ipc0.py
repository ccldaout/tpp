from tpp import threadutil as tu
from tpp import toolbox as tb
from tpp import ipc
import threading

addr = ('localhost', 55222)

class Service(ipc.ServiceBase):
    def __init__(self, *args, **kwargs):
        self._lock = tu.Lock()
        self._users = {}

    # ['greet', 'name']
    def handle_greet(self, port, msg):
        print 'greeted', port, msg[1]
        with self._lock:
            self._users[port] = msg[1]
        self.sendto_all(['notify', '<server>', 'greeted', msg[1]])

    # ['say', string...]
    def handle_say(self, port, msg):
        try:
            name = self._users[port]
        except:
            name = 'x'
        self.sendto_all(['notify', name, msg[1]])

    # ['bye']
    def handle_bye(self, port, msg):
        try:
            name = self._users[port]
        except:
            name = 'x'
        self.sendto_all(['notify', name, 'bye'])

    def handle_ACCEPTED(self, port):
        print '*accepted*', port
        with self._lock:
            self._users[port] = '?'
        port.send(['who'])

    def handle_DISCONNECTED(self, port):
        print '*disconnected*', port
        with self._lock:
            self._users.pop(port, None)

    def handle_SOCKERROR(self, port):
        print '*sockerror*', port
        with self._lock:
            self._users.pop(port, None)

class Client(ipc.ServiceBase):

    def __init__(self, name):
        self.name = name

    # ['who']
    def handle_who(self, port, msg):
        port.send(['greet', self.name])
        pass

    # ['notify', 'name', string...]
    def handle_notify(self, port, msg):
        print msg

    def handle_CONNECTED(self, port):
        print '*connected*'

    def handle_DISCONNECTED(self, port):
        print '*disconnected*'

def server(background=True):
    ipc.Acceptor(Service(), addr).start(background)

def client(name):
    return ipc.Connector(Client(name), addr, recover=True).start().port

def simple():
    return ipc.SimpleClient(addr)

print
print "server() / port = client('name') / sc = simple()"
print
