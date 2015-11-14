# -*- coding: utf-8 -*-

import imp
import json
import os
import os.path
import sys
import traceback
from StringIO import StringIO
from zipfile import PyZipFile, ZipFile
from tpp import rpc
from tpp import toolbox as tb

___ = tb.no_except

#----------------------------------------------------------------------------
#----------------------------------------------------------------------------

def make_zipstr(pkgroot):
    sf = StringIO()
    pyzip = PyZipFile(sf, 'w')
    pyzip.writepy(os.path.expanduser(pkgroot))
    pyzip.close()
    zipcontents = sf.getvalue()
    sf.close()
    return zipcontents

def make_unzipstr(zippedstr, pkgstore):
    sf = StringIO(zippedstr)
    pyzip = ZipFile(sf, 'r')
    pyzip.extractall(os.path.expanduser(pkgstore))
    pyzip.close()

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

    def get_pkginfo(self, pkgname):
        try:
            with open(self._cfpath) as f:
                conf = json.load(f)
            dirs = conf.get('EXPORTS', ['~/tpp.remotepkg/exports'])
            for d in dirs:
                pkgtop = os.path.join(tb.fn.eval(d), pkgname)
                sno = int(___(os.path.getmtime, 0)(pkgtop))
                if sno:
                    return pkgtop, sno
        except:
            return None, None

    @rpc.export
    def get_serial(self, pkgname):
        path, sno = self.get_pkginfo(pkgname)
        return sno

    @rpc.export
    def get_zip(self, pkgname):
        path, sno = self.get_pkginfo(pkgname)
        if path:
            return ___(make_zipstr, None)(path)
        else:
            return None

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
        self._storecache = {}
        conf = tb.fn.eval(conf)
        try:
            self._conf = {}
            with open(conf) as f:
                self._conf = json.load(f)
        except:
            self._conf = {'STORE':'store-directory',
                          'TMO_s':0.2,
                          'PKGDB':{'pkg-name':('host-name', 55222),
                                   'pkg-name2':('host-name2', 55222)}}
            if not os.path.exists(conf):
                ___(os.makedirs)(os.path.dirname(conf))
                with open(conf, 'w') as f:
                    json.dump(self._conf, f, sort_keys=True, indent=2)

    def _get_pkginfo(self, topname):
        store = self._conf.get('STORE', '~/tmp/tpp.remotepkg')
        pkgdb = self._conf.get('PKGDB', {})
        tmo_s = self._conf.get('TMO_s', 0.2)
        addr = pkgdb.get(topname, None)
        if addr and store:
            return addr, tb.fn.eval(store), tmo_s
        return None, None, None

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

    def _loadpkg_if(self, topname):
        addr, store, tmo_s = self._get_pkginfo(topname)
        if addr is None:
            return None

        api = ___(rpc.client)(tuple(addr), initmo_s=tmo_s, background=False, lazy_setup=False)
        if api is None:
            if os.path.isdir(os.path.join(store, topname)):
                return store
            return None
        server_sno = api.get_serial(topname)
        if server_sno is None:
            return None

        local_sno = self._get_sno(store, topname)
        if isinstance(local_sno, int) and local_sno == server_sno:
            return store

        ___(os.makedirs)(store)
        zs = api.get_zip(topname)
        if zs is None:
            return None
        make_unzipstr(zs, store)
        self._put_sno(store, topname, server_sno)

        return store

    def find_module(self, modname, paths=None):
        topname = modname.split('.')[0]

        if topname in self._storecache:
            store = self._storecache[topname]
        else:
            store = self._loadpkg_if(topname)
            self._storecache[topname] = store
        if store is None:
            return None
        
        name_fs = modname.replace('.', os.path.sep)
        path_fs = os.path.join(store, name_fs)

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
        print 'Usage: remotepkg host:port [server-conf]'
        exit(1)
    addr = sys.argv[1].split(':')
    addr[1] = int(addr[1])
    if len(addr) == 3:
        conf = sys.argv[2]
    else:
        conf = '~/.tpp/remotepkg/server.json'
    server(tuple(addr), conf)
else:
    conf = '~/.tpp/remotepkg/client.json'
    sys.meta_path.append(Finder(conf))
