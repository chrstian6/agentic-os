import os
import shutil
import tempfile

DIST = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAYLOAD = os.path.join(DIST, "payload")


def tmpdir():
    return tempfile.mkdtemp(prefix="aos-test-")


def rm(path):
    shutil.rmtree(path, ignore_errors=True)


def write(path, content):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content)
    return path
