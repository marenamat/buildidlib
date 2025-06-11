#import gnupg
import gzip
import lzma
import requests
import sys


class DownloaderException(Exception):
    def __init__(self, code: int, msg: str, **kwargs):
        self.code = code
        self.msg = msg
        super().__init__(f"{msg}: Download failed ({code})")

class DownloadSuccessful(DownloaderException):
    pass

class DownloadNotFound(DownloaderException):
    pass

class Downloader:
    def __init__(self, url):
        if url[-1] != "/":
            url += "/"
        self.url = url

    def _handle_result(self, req):
        try:
            raise {
                    200: DownloadSuccessful,
                    404: DownloadNotFound,
                    }[req.status_code](req.url, req.status_code)
        except KeyError:
            raise DownloaderException(req.url, req.status_code)

    def load_raw(self, what):
        req = requests.get(self.url + what, stream=True)
        if req.status_code == 200:
            return req.raw
        else:
            return self._handle_result(req)

    def load(self, what):
        req = requests.get(self.url + what, stream=True)
        if req.status_code == 200:
            return req.content.decode()
        else:
            return self._handle_result(req)

class Package:
    def __init__(self, package_list):
        self.package_list = package_list
        self.info = {}
        self.last = None

    def line(self, line):
        assert(line[-1] == "\n")
        if len(line) == 1:
            self.package_list._packages[self.info["Package"]] = self
            return Package(self.package_list)

        if line.startswith(" "):
            assert(self.last is not None)
            self.info[self.last] += line[:-1]
        else:
            k, v = line.split(": ", 1)
            assert(k not in self.info)
            self.info[k] = v[:-1]
            self.last = k

        return self

#    def done(self):
#        if "Build-Ids" in self.info:
#            for f in self.info["Build-Ids"].split(" "):
#                print(f"BID;{f};{self.info['SHA256']}")
#            print(f"SHA;{self.info['SHA256']};{self.info['Package']};{self.info['Version']}")

class PackageException(Exception):
    pass

class Packages(Downloader):
    def __init__(self, release, component, architecture):
        self.release = release
        self.component = component
        self.architecture = architecture
        super().__init__(f"{release.url}{component}/binary-{architecture}/")

    def process_packages(self, stream):
        self._packages = {}
        cur = Package(self)
        for lb in stream:
            cur = cur.line(lb.decode())
        if cur.last is not None:
            cur.line("\n")

    @property
    def packages(self):
        try:
            return self._packages
        except AttributeError:
            pass

        try:
            with lzma.open(self.load_raw("Packages.xz"), "rb") as p:
                self.process_packages(p)
        except DownloadNotFound:
            try:
                with gzip.open(self.load_raw("Packages.gz"), "rb") as p:
                    self.process_packages(p)
            except DownloadNotFound:
                try:
                    self.process_packages(self.load_raw("Packages"))
                except DownloadNotFound:
                    raise PackageException(f"No Packages file at {self.url}")

        return self._packages

    def __iter__(self):
        return self.packages.values().__iter__()

class ReleaseException(Exception):
    pass

class Release(Downloader):
    def __init__(self, base, name):
        super().__init__(base.url + "dists/" + name)
        self.base = base
        self.name = name[:-1]

    @property
    def release(self):
        try:
            return self._release
        except AttributeError:
            pass

        try:
            self._release = self.load("Release")
            self._release_sig = self.load("Release.gpg")
            # TODO: actually check the release signature
        except DownloadNotFound:
            try:
                inrelease = self.load("InRelease")
            except DownloadNotFound:
                raise ReleaseException(f"No (In)Release found at {self.url}")

            try:
                # TODO: check the signature
                empty, relbeg = inrelease.split("-----BEGIN PGP SIGNED MESSAGE-----\n\n")
                assert(empty == "")
                self._release, trailer = relbeg.split("\n-----BEGIN PGP SIGNATURE-----\n\n")
                assert(trailer == "")
            except Exception as e:
                raise ReleaseException(f"Strange InRelease contents at {self.url}") from e

        array_value = None
        self._release_dict = {}
        for line in self._release.strip().split("\n"):
            if line[0] == " ":
                array_value.append(line[1:])
            elif line[-1] == ":":
                array_value = []
                assert((key := line[:-1]) not in self._release_dict)
                self._release_dict[key] = array_value
                self._release_dict[key.replace("-", "_").lower()] = array_value
            else:
                key, value = line.split(": ", maxsplit=1)
                self._release_dict[key] = value
                self._release_dict[key.replace("-", "_").lower()] = value
                array_value = None

        return self._release

    @property
    def info(self):
        return f"Release(url={self.url})"

    @property
    def architectures(self):
        try:
            return self._architectures
        except AttributeError:
            pass

        self._architectures = self.Architectures.split(" ")
        return self._architectures
        
    @property
    def components(self):
        try:
            return self._components
        except AttributeError:
            pass

        self._components = self.Components.split(" ")
        return self._components

    @property
    def package_lists(self):
        try:
            return self._package_lists
        except AttributeError:
            pass

        self._package_lists = [
                Packages(release=self, component=c, architecture=a)
                for c in self.components
                for a in ("all", *self.architectures)
                ]

        return self._package_lists

    def __getattr__(self, name):
        if name[0] == "_":
            raise AttributeError(f"Release has no attribute '{name}'")

        _ = self.release
        try:
            return self._release_dict[name]
        except KeyError as e:
            raise AttributeError(f"Release has no attribute '{name}'") from e

class Repository(Downloader):
    @property
    def releases(self):
        try:
            return self._releases
        except AttributeError:
            pass

        self._releases = [
                Release(self, d)
                for d in [ s.split('"')[0] for s in self.load("dists/").split('<a href="')[1:] ]
                if d[0] != "/" and d[-1] == "/"
                ]
        return self._releases

    def __iter__(self):
        return self.releases.__iter__()

r = Repository("http://ftp.cz.debian.org/debian/")
for rel in r:
    for pl in rel.package_lists:
#        print("PACKAGELIST", pl)
        try:
            for p in pl:
                print(f"PACKAGE {p.info['Package']} in {pl.component} / {pl.architecture}")
                if "Build-Ids" in p.info:
                    print("BUILDIDS", p.info["Build-Ids"])
        except PackageException as e:
            print(f"Failed to load packages for {pl.component} / {pl.architecture}: {e}")
