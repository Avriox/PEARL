import time
import random
from sortedcontainers import SortedList, SortedDict, SortedSet

def main():
    random.seed(0)
    sizes = [ 30000]  # adjust sizes for runtime scaling


    for size in sizes:
        # --------------------
        # SortedList benchmark
        # --------------------
        data = list(range(size))
        random.shuffle(data)
        sl = SortedList()
        for x in data:
            sl.add(x)
        _ = sl.count(size // 2)
        _ = sl[-10:]

        # --------------------
        # SortedDict benchmark
        # --------------------
        data = list(range(size))
        random.shuffle(data)
        sd = SortedDict()
        for x in data:
            sd[x] = x
        _ = sd.popitem(index=-1)
        _ = list(sd.keys())[:10]

        # --------------------
        # SortedSet benchmark
        # --------------------
        data = list(range(size))
        random.shuffle(data)
        ss = SortedSet()
        ss.update(data)
        _ = ss.bisect_left(size // 2)

if __name__ == "__main__":
    main()