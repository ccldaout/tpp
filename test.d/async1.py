from tpp.threadutil import pr, async, test_cancel

import time
def action(cnt):
    def cleaner():
        pr('action: canceled')
    for n in range(cnt):
        pr('action: %d/%d', n, cnt)
        time.sleep(1)
        test_cancel(cleaner)
    return n
at = async(action, 5)
time.sleep(3)		# 3 or 6
at.cancel()
pr('main: result ...')
try:
    res = at.result
except Exception as e:
    res = e
pr('main: result ... %s', res)
