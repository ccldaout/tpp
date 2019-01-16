#!/usr/bin/python
# -*- coding: utf-8 -*-

import code
import sys
from tpp import rpc
from tpp import threadutil as tu

#----------------------------------------------------------------------------
#                             server side code
#----------------------------------------------------------------------------

class _Writer(object):
    def __init__(self, *writers):
        self._writers = writers

    def write(self, data):
        for w in self._writers:
            try:
                w(data)
            except:
                pass

class _Console(code.InteractiveConsole):
    def __init__(self, ldic=None):
        # [CAUTION] code.InterativeConsole is OLD-TYPE class.
        code.InteractiveConsole.__init__(self, ldic)
        self._lock = tu.Lock()
        self._cur_cid = None
        self._receiver = None
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        sys.stdout = _Writer(self._stdout.write, self._forward)
        sys.stderr = _Writer(self._stderr.write, self._forward)

    def raw_input(prompt=':'):
        raise NotImplementedError('raw_input')

    def _forward(self, data):
        with self._lock:
            receiver = self._receiver
        if receiver:
            receiver(data)

    @rpc.export
    def attach(self, cid__, receiver):
        with self._lock:
            if self._cur_cid is not None:
                raise RuntimeError('Console is used by other client.')
            self._cur_cid = cid__
            self._receiver = receiver
            self._stdout.write('\n[ Remote console is attached ]\n\n')

    @rpc.export
    def detach(self, cid__):
        with self._lock:
            if self._cur_cid == cid__:
                self._cur_cid = None
                self._receiver = None
                self._stdout.write('\n[ Remote console is dettached ]\n\n')

    @rpc.export
    def input(self, cid__, s):
        with self._lock:
            if self._cur_cid != cid__:
                raise RuntimeError('Console is used by other client.')
        self._stdout.write(s)
        self._stdout.write('\n')
        return self.push(s)

    def on_disconnection(self, cid__):
        self.detach(cid__)

def server(addr, dic=None, background=True):
    if dic is None:
        dic = globals()
    rpc.server(addr, [_Console(dic)], background=background)

#----------------------------------------------------------------------------
#                             client side code
#----------------------------------------------------------------------------

def client(addr):
    @rpc.export(quick=True, no_reply=True)
    def receiver(s):
        return sys.stdout.write(s)
    api = rpc.client(addr)
    api.attach(receiver)
    ps1 = 'con> '
    ps2 = '.... '
    try:
        while True:
            prompt = ps1
            while True:
                s = raw_input(prompt)
                if not api.input(s):
                    break
                prompt = ps2
    except:
        api.detach()

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []

if __name__ == '__main__':
    sys.argv.pop(0)
    if not sys.argv:
        print 'Usage: rcon host:port'
    else:
        try:
            import readline
        except:
            pass
        client(sys.argv[0])
