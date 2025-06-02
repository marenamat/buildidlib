import requests
import sys

r = requests.get(sys.argv[1], stream=True)

class DebianPackageManifest:
    def __init__(self):
        self.last = None
        self.info = {}

    def line(self, line):
        if line.startswith(" "):
            assert(self.last is not None)
            self.info[self.last] += line
        else:
            k, v = line.split(": ", 1)
            assert(k not in self.info)
            self.info[k] = v

    def done(self):
        if "Build-Ids" in self.info:
            for f in self.info["Build-Ids"].split(" "):
                print(f"BID;{f};{self.info['SHA256']}")
            print(f"SHA;{self.info['SHA256']};{self.info['Package']};{self.info['Version']}")

cur = DebianPackageManifest()
for line in r.iter_lines():
    if line:
        continue

    if line == "":
        cur.done()
        cur = DebianPackageManifest()
    else:
        cur.line(line)

cur.done()
