import gzip
import requests
import sys

class DebianPackageManifest:
    def __init__(self):
        self.last = None
        self.info = {}

    def line(self, line):
#        print(line)
        if line.startswith(" "):
            assert(self.last is not None)
            self.info[self.last] += line
        else:
            k, v = line.split(": ", 1)
            assert(k not in self.info)
            self.info[k] = v
            self.last = k

    def done(self):
        if "Build-Ids" in self.info:
            for f in self.info["Build-Ids"].split(" "):
                print(f"BID;{f};{self.info['SHA256']}")
            print(f"SHA;{self.info['SHA256']};{self.info['Package']};{self.info['Version']}")

r = requests.get(sys.argv[1], stream=True)
g = gzip.open(r.raw, "r")

cur = DebianPackageManifest()
for lb in g:
    line = lb.decode()
    assert(line[-1] == "\n")

    if len(line) == 1:
        cur.done()
#        print("Done package", cur.info['Package'])
        cur = DebianPackageManifest()
    else:
        cur.line(line[:-1])

cur.done()
