from tpp import threadutil as tu
from tpp import toolbox as tb
from tpp import rpc
import threading

#tu.pr.print_name = True

addr = ('localhost', 55222)

class Service(object):
    @rpc.export(quick=True)
    def toupper(self, s):
        '''string to upper'''
        tu.pr('toupper: %s', s)
        return s.upper()

    @rpc.export(name='allplus')
    def total(self, cid__, *args):
        '''sum of arguments'''
        tu.pr('total: cid__: %s, args: < %s >', cid__, args)
        return sum(args)
        
    @rpc.export
    def apply(self, lis, func):
        if func is None:
            func = self.show
        tu.pr('apply: %s', lis)
        return [func(v) for v in lis]

    def show(self, v):
        return v

def server():
    rpc.server(addr, [Service()], thread_max=32, thread_lwm=8)

api = None

def client():
    global api
    api = rpc.client(addr)

def show(v):
    print 'show:', v
    return v * 10

print
print "server() / client()"
print
