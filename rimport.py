# -*- coding: utf-8 -*-

import glob
import imp
import json
import os
import os.path
import sys
import traceback
from StringIO import StringIO
import tarfile
from tpp import rpc
from tpp import toolbox as tb

___ = tb.no_except

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

def archive(pkgroot):
    sf = StringIO()
    ar = tarfile.open(fileobj=sf, mode='w')
    ar.add(os.path.expanduser(pkgroot), arcname=os.path.basename(pkgroot))
    ar.close()
    ar_str = sf.getvalue()
    sf.close()
    return ar_str

def unarchive(ar_str, pkgcache):
    sf = StringIO(ar_str)
    ar = tarfile.open(fileobj=sf, mode='r')
    ar.extractall(os.path.expanduser(pkgcache))
    ar.close()

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

class PkgService(object):
    def __new__(cls, cfpath):
        self = super(PkgService, cls).__new__(cls)
        self._cfpath = tb.fn.eval(cfpath)
        if not os.path.exists(self._cfpath):
            try:
                ___(os.makedirs)(os.path.dirname(self._cfpath))
                with open(self._cfpath, 'w') as f:
                    data = {'EXPORTS':['pkg-parent-directory',
                                       'pkg-parent-directory2']}
                    json.dump(data, f, sort_keys=True, indent=2)
            except:
                traceback.print_exc()
        return self

    def _get_exports(self):
        es = {}
        dirs = ['~/.tpp/rimport/exports']
        try:
            with open(self._cfpath) as f:
                conf = json.load(f)
            dirs = conf.get('EXPORTS', dirs)
        except:
            pass
        for d in dirs:
            d = tb.fn.eval(d)
            for pkgd in glob.glob(os.path.join(d, '*')):
                ini = os.path.join(pkgd, '__init__.py')
                if os.path.isdir(pkgd) and os.path.isfile(ini):
                    pkgn = os.path.basename(pkgd)
                    if pkgn not in es:
                        es[pkgn] = pkgd
        return es

    @rpc.export
    def get_exports(self):
        return self._get_exports().keys()

    @rpc.export
    def get_serial(self, pkgname):
        pkgd = self._get_exports().get(pkgname, None)
        return int(___(os.path.getmtime, 0)(pkgd))

    @rpc.export
    def get_archive(self, pkgname):
        pkgd = self._get_exports().get(pkgname, None)
        return ___(archive, None)(pkgd)

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

class Loader(object):
    def __init__(self, name, path, desc):
        self.name = name
        self.path = path
        self.desc = desc

    def load_module(self, name):
        if self.desc[2] == imp.PKG_DIRECTORY:
            return imp.load_module(self.name, None, self.path, self.desc)
        else:
            return imp.load_module(self.name, open(self.path), self.path, self.desc)
        
class Finder(object):
    def __init__(self, conf):
        self._pkgcache = {}
        self._svrcache = {}
        conf = tb.fn.eval(conf)
        try:
            self._conf = {}
            with open(conf) as f:
                self._conf = json.load(f)
            self._setup_svrcache()
        except:
            self._conf = {'CACHE':'~/.tpp/rimport/cache',
                          'TMO_s':0.2,
                          'SERVER':[('localhost', 55222)]}
            if not os.path.exists(conf):
                ___(os.makedirs)(os.path.dirname(conf))
                with open(conf, 'w') as f:
                    json.dump(self._conf, f, sort_keys=True, indent=2)

    def _setup_svrcache(self):
        tmo_s = self._get_tmo_s()
        svrs = self._get_servers()
        for addr in svrs:
            api = ___(rpc.client)(tuple(addr), itmo_s=0.05, ctmo_s=tmo_s,
                                  background=False, lazy_setup=False)
            if api:
                for pkg in api.get_exports():
                    self._svrcache[pkg] = tuple(addr)

    def _get_cache(self):
        return tb.fn.eval(self._conf.get('CACHE', '~/.tpp/rimport/cache'))

    def _get_tmo_s(self):
        return self._conf.get('TMO_s', 0.2)
        
    def _get_servers(self):
        return self._conf.get('SERVER', [])

    def _get_sno(self, store, topname):
        s = os.path.join(store, topname)
        if not os.path.exists(s):
            return None
        s = os.path.join(store, topname + '.serial')
        try:
            with open(s) as f:
                return int(f.read())
        except:
            return None

    def _put_sno(self, store, topname, sno):
        s = os.path.join(store, topname + '.serial')
        try:
            with open(s, 'w') as f:
                f.write(str(sno))
        except:
            traceback.print_exc()

    def _select_server(self, topname):
        tmo_s = self._get_tmo_s()
        addr = self._svrcache.get(topname, None)
        if addr is None:
            return None
        return  ___(rpc.client)(addr, itmo_s=0.05, ctmo_s=tmo_s,
                                background=False, lazy_setup=False)

    def _loadpkg_if(self, topname):
        cache = self._get_cache()

        api = self._select_server(topname)
        if api is None:
            if os.path.isdir(os.path.join(cache, topname)):
                return cache
            return None

        server_sno = api.get_serial(topname)
        if server_sno is None:
            return None

        local_sno = self._get_sno(cache, topname)
        if isinstance(local_sno, int) and local_sno == server_sno:
            return cache

        ___(os.makedirs)(cache)
        ar = api.get_archive(topname)
        if ar is None:
            return None
        unarchive(ar, cache)
        self._put_sno(cache, topname, server_sno)

        return cache

    def find_module(self, modname, paths=None):
        pkgtop = modname.split('.')[0]

        if pkgtop in self._pkgcache:
            cache = self._pkgcache[pkgtop]
        else:
            cache = self._loadpkg_if(pkgtop)
            self._pkgcache[pkgtop] = cache
        if cache is None:
            return None
        
        name_fs = modname.replace('.', os.path.sep)
        path_fs = os.path.join(cache, name_fs)

        if os.path.isdir(path_fs):
            return Loader(modname, path_fs, ('', '', imp.PKG_DIRECTORY))
        for sfx in ['.pyc', '.py']:
            path_py = path_fs + sfx
            if os.path.exists(path_py):
                desc = [t for t in imp.get_suffixes() if t[0] == sfx][0]
                return Loader(modname, path_py, desc)
        return None

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

__all__ = []

if __name__ == '__main__':
    def server(addr, conf):
        rpc.server(addr, [PkgService(conf)], background=False)
    if len(sys.argv) == 1:
        print 'Usage: rimport host:port [server-conf]'
        exit(1)
    addr = sys.argv[1].split(':')
    addr[1] = int(addr[1])
    if len(addr) == 3:
        conf = sys.argv[2]
    else:
        conf = '~/.tpp/rimport/server.json'
    server(tuple(addr), conf)
else:
    conf = '~/.tpp/rimport/client.json'
    sys.meta_path.append(Finder(conf))
