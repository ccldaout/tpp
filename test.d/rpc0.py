from tpp import threadutil as tu
from tpp import toolbox as tb
from tpp import rpc
import threading

addr = ('localhost', 55222)

class Service(object):
    @rpc.export
    def toupper(self, s):
        '''string to upper'''
        tu.pr('Service.toupper(%s)', s)
        return s.upper()

    @rpc.export('allplus')
    def total(self, cid__, *args):
        '''sum of arguments'''
        tu.pr('cid__: %s, args: < %s >', cid__, args)
        return sum(args)
        
    @rpc.export()
    def apply(self, lis, func):
        return [func(v) for v in lis]

def server():
    rpc.server(addr, [Service()])

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
