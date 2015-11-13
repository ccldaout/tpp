import time
from tpp import async
from tpp import threadutil as _tu

def pr(fmt, *args):
    _tu.pr(_tu.current_thread().name + ': ' + fmt, *args)
    #_tu.pr(fmt, *args)

def third(name, sec, val):
    pr('third : %s ...', name)
    yield async.call(time.sleep, sec)
    pr('third : %s ... end (-->%s)', name, val)
    yield async.return_(val)

def second(name, sec, val):
    pr('second: %s ...', name)
    v = yield third(name, sec, val*100 + 1)
    pr('second: %s ... %s', name, v)
    v = yield third(name, sec, val*100 + 2)
    pr('second: %s ... %s', name, v)
    v = yield third(name, sec, val*100 + 3)
    pr('second: %s ... %s (end)', name, v)
    yield async.return_(val*100+99)

def first(name, sec, val):
    pr('first : %s ...', name)
    v = yield second(name, sec, val*100 + 8)
    pr('first : %s ... %s (end)', name, v)

async.spool(first, 'aaa', 2.6, 1)
async.spool(first, 'bbb', 2.2, 2)
async.spool(first, 'ccc', 2.5, 3)
async.start(daemon=False)
time.sleep(8)
async.stop()
async.wait()
