#!/usr/bin/env python3
"""
Selection sort demo with a known performance issue (O(n^2) algorithm).
"""

from typing import List, Optional, Tuple, Callable
import argparse
import random
import time


def generate_numbers(n: int, seed: Optional[int] = None) -> List[int]:
    """Generate n random ints."""
    rng = random.Random(seed)
    return [rng.randint(0, 10_000) for _ in range(n)]


# [ISSUE START: (Inefficient algorithms)]
def selection_sort(nums: List[int]) -> List[int]:
    """
    Intentionally inefficient O(n^2) selection sort.
    A faster alternative would be the built-in sorted() (Timsort, O(n log n) average).
    """
    arr = nums[:]  # work on a copy
    for i in range(len(arr)):
        min_idx = i
        for j in range(i + 1, len(arr)):
            if arr[j] < arr[min_idx]:
                min_idx = j
        arr[i], arr[min_idx] = arr[min_idx], arr[i]
    return arr


# [ISSUE END: (Inefficient algorithms)]


def timed_call(fn: Callable, *args, **kwargs) -> Tuple[object, float]:
    """Run fn(*args, **kwargs) and return (result, elapsed_seconds)."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Selection sort with an intentional O(n^2) performance issue."
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1000,
        help="Number of random integers to sort (default: 1000)",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed (default: 42)"
    )
    args = parser.parse_args()

    data = generate_numbers(args.n, seed=args.seed)
    sorted_data, dt = timed_call(selection_sort, data)

    print(
        f"Sorted {len(data)} numbers in {dt:.4f}s using selection sort (intentionally O(n^2))."
    )
    preview = ", ".join(map(str, sorted_data[:10]))
    print(f"Preview of first 10 sorted numbers: [{preview}]")


if __name__ == "__main__":
    main()
