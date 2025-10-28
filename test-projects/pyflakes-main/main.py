import os

from pyflakes.api import checkPath
from pyflakes.reporter import Reporter

def main():
    base = os.path.join(os.path.dirname(__file__), "pyflakes")

    files_to_check = [
        os.path.join(base, "checker.py"),
        os.path.join(base, "messages.py"),
        os.path.join(base, "reporter.py"),
        os.path.join(base, "api.py"),
    ]

    devnull = open(os.devnull, "w")
    reporter = Reporter(devnull, devnull)

    for _ in range(2):  # adjust upward until runtime feels good
        for f in files_to_check:
            checkPath(f, reporter)

if __name__ == "__main__":
   main()

