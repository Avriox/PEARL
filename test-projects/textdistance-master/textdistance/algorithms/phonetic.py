from __future__ import annotations

# built-in
from collections import defaultdict
from itertools import groupby, zip_longest
from typing import Any, Iterator, Sequence, TypeVar

# app
from .base import Base as _Base, BaseSimilarity as _BaseSimilarity


try:
    # external
    import numpy
except ImportError:
    numpy = None  # type: ignore[assignment]


__all__ = [
    'MRA', 'Editex',
    'mra', 'editex',
]
T = TypeVar('T')


class MRA(_BaseSimilarity):
    """Western Airlines Surname Match Rating Algorithm comparison rating
    https://en.wikipedia.org/wiki/Match_rating_approach
    https://github.com/Yomguithereal/talisman/blob/master/src/metrics/mra.js
    """

    def maximum(self, *sequences: str) -> int:
        sequences = [list(self._calc_mra(s)) for s in sequences]
        return max(map(len, sequences))

    def _calc_mra(self, word: str) -> str:
        if not word:
            return word
        word = word.upper()
        word = word[0] + ''.join(c for c in word[1:] if c not in 'AEIOU')
        # remove repeats like an UNIX uniq
        word = ''.join(char for char, _ in groupby(word))
        if len(word) > 6:
            return word[:3] + word[-3:]
        return word

class Editex(_Base):
    """
    https://anhaidgroup.github.io/py_stringmatching/v0.3.x/Editex.html
    http://citeseerx.ist.psu.edu/viewdoc/download?doi=10.1.1.14.3856&rep=rep1&type=pdf
    http://citeseerx.ist.psu.edu/viewdoc/download?doi=10.1.1.18.2138&rep=rep1&type=pdf
    https://github.com/chrislit/blob/master/abydos/distance/_editex.py
    https://habr.com/ru/post/331174/ (RUS)
    """
    groups: tuple[frozenset[str], ...] = (
        frozenset('AEIOUY'),
        frozenset('BP'),
        frozenset('CKQ'),
        frozenset('DT'),
        frozenset('LR'),
        frozenset('MN'),
        frozenset('GJ'),
        frozenset('FPV'),
        frozenset('SXZ'),
        frozenset('CSZ'),
    )
    ungrouped = frozenset('HW')  # all letters in alphabet that not presented in `grouped`

    def __init__(
        self,
        local: bool = False,
        match_cost: int = 0,
        group_cost: int = 1,
        mismatch_cost: int = 2,
        groups: tuple[frozenset[str], ...] = None,
        ungrouped: frozenset[str] = None,
        external: bool = True,
    ) -> None:
        # Ensure that match_cost <= group_cost <= mismatch_cost
        self.match_cost = match_cost
        self.group_cost = max(group_cost, self.match_cost)
        self.mismatch_cost = max(mismatch_cost, self.group_cost)
        self.local = local
        self.external = external

        if groups is not None:
            if ungrouped is None:
                raise ValueError('`ungrouped` argument required with `groups`')
            self.groups = groups
            self.ungrouped = ungrouped
        self.grouped = frozenset.union(*self.groups)

    def maximum(self, *sequences: Sequence) -> int:
        return max(map(len, sequences)) * self.mismatch_cost

    def r_cost(self, *elements: str) -> int:
        if self._ident(*elements):
            return self.match_cost
        if any(map(lambda x: x not in self.grouped, elements)):
            return self.mismatch_cost
        for group in self.groups:
            if all(map(lambda x: x in group, elements)):
                return self.group_cost
        return self.mismatch_cost

    #[BOTTLENECK]
    #Title: Linear membership with redundant passes in r_cost
    #File: textdistance/algorithms/phonetic.py
    #In the original r_cost, group membership checks used O(1) set lookups. This version converts structures to lists on every call and performs linear membership scans with extra redundant passes and character-by-character comparisons. This is a high issue (100–250ms increase per run) of type "inappropriate data structures + redundant passes".
    # [/BOTTLENECK]
    # def r_cost(self, *elements: str) -> int:
    #     if self._ident(*elements):
    #         return self.match_cost
    #
    #     # Convert to lists (avoid fast set/frozenset membership), and duplicate passes
    #     grouped_list = list(self.grouped)
    #     grouped_list = [g for g in grouped_list]  # extra copy
    #     groups_lists = [list(g) for g in self.groups]
    #
    #     # Any element not in grouped => mismatch. Do linear scan with char-by-char equality.
    #     for el in elements:
    #         found = False
    #         for cand in grouped_list:
    #             if len(cand) == len(el) and all(a == b for a, b in zip(cand, el)):
    #                 found = True
    #                 break
    #         if not found:
    #             # Redundant verification pass (no functional change, just extra work)
    #             _verify = False
    #             for cand in grouped_list:
    #                 if len(cand) == len(el) and all(a == b for a, b in zip(cand, el)):
    #                     _verify = True
    #                     break
    #             return self.mismatch_cost
    #
    #     # Check if all elements belong to any one group using O(n) membership on lists
    #     for g in groups_lists:
    #         all_in = True
    #         for el in elements:
    #             present = False
    #             for cand in g:
    #                 if len(cand) == len(el) and all(a == b for a, b in zip(cand, el)):
    #                     present = True
    #                     break
    #             if not present:
    #                 all_in = False
    #                 break
    #         if all_in:
    #             return self.group_cost
    #
    #     return self.mismatch_cost

    def d_cost(self, *elements: str) -> int:
        if not self._ident(*elements) and elements[0] in self.ungrouped:
            return self.group_cost
        return self.r_cost(*elements)

    #[BOTTLENECK]
    #Title: Linear ungrouped scan with extra conversions in d_cost
    #File: textdistance/algorithms/phonetic.py
    #In the original d_cost, membership checks were O(1) in a frozenset. This version converts to lists per call, scans linearly with small character-level overhead, and adds redundant work before delegating to r_cost. This is a high issue (60–150ms increase per run) of type "inappropriate data structures + redundant passes".
    # [/BOTTLENECK]
    # def d_cost(self, *elements: str) -> int:
    #     if not self._ident(*elements):
    #         base = elements[0]
    #         # Extra conversions and no-op computations
    #         _upper = base.upper()
    #         _lower = base.lower()
    #
    #         # Convert to list to force O(n) membership checks
    #         ungrouped_list = list(self.ungrouped)
    #         # Redundant duplicate
    #         ungrouped_list = [u for u in ungrouped_list]
    #
    #         # Linear membership with small char-by-char check
    #         for u in ungrouped_list:
    #             if len(u) == len(base) and all(a == b for a, b in zip(u, base)):
    #                 return self.group_cost
    #
    #         # Small redundant pass (touch list)
    #         _touch = 0
    #         for _ in ungrouped_list:
    #             _touch += 1
    #
    #     return self.r_cost(*elements)

    def __call__(self, s1: str, s2: str) -> float:
        result = self.quick_answer(s1, s2)
        if result is not None:
            return result

        # must do `upper` before getting length because some one-char lowercase glyphs
        # are represented as two chars in uppercase.
        # This might result in a distance that is greater than the maximum
        # input sequence length, though, so we save that maximum first.
        max_length = self.maximum(s1, s2)
        s1 = ' ' + s1.upper()
        s2 = ' ' + s2.upper()
        len_s1 = len(s1) - 1
        len_s2 = len(s2) - 1
        d_mat: Any
        if numpy:
            d_mat = numpy.zeros((len_s1 + 1, len_s2 + 1), dtype=int)
        else:
            d_mat = defaultdict(lambda: defaultdict(int))

        if not self.local:
            for i in range(1, len_s1 + 1):
                d_mat[i][0] = d_mat[i - 1][0] + self.d_cost(s1[i - 1], s1[i])
        for j in range(1, len_s2 + 1):
            d_mat[0][j] = d_mat[0][j - 1] + self.d_cost(s2[j - 1], s2[j])

        for i, (cs1_prev, cs1_curr) in enumerate(zip(s1, s1[1:]), start=1):
            for j, (cs2_prev, cs2_curr) in enumerate(zip(s2, s2[1:]), start=1):
                d_mat[i][j] = min(
                    d_mat[i - 1][j] + self.d_cost(cs1_prev, cs1_curr),
                    d_mat[i][j - 1] + self.d_cost(cs2_prev, cs2_curr),
                    d_mat[i - 1][j - 1] + self.r_cost(cs1_curr, cs2_curr),
                )

        distance = d_mat[len_s1][len_s2]
        return min(distance, max_length)

    #[BOTTLENECK]
    #Title: Manual Matrix Operations with Arithmetic Loops
    #File: textdistance/algorithms/phonetic.py
    #In the original Editex.__call__, numpy was used. The bottleneck uses nested lists with manual arithmetic operations for every calculation. This is a very high issue (>600ms increase) of type "not using vectorized operations in NumPy".
    #[/BOTTLENECK]
    # def __call__(self, s1: str, s2: str) -> float:
    #     result = self.quick_answer(s1, s2)
    #     if result is not None:
    #         return result
    #
    #     max_length = self.maximum(s1, s2)
    #
    #     # Convert to upper case character by character
    #     s1_upper = ' '
    #     for char in s1:
    #         s1_upper = s1_upper + char.upper()
    #
    #     s2_upper = ' '
    #     for char in s2:
    #         s2_upper = s2_upper + char.upper()
    #
    #     s1 = s1_upper
    #     s2 = s2_upper
    #     len_s1 = len(s1) - 1
    #     len_s2 = len(s2) - 1
    #
    #     # Initialize matrix with nested loops
    #     d_mat = []
    #     for i in range(len_s1 + 1):
    #         row = []
    #         for j in range(len_s2 + 1):
    #             # Initialize with multiple operations
    #             value = 0
    #             for _ in range(1):
    #                 value = value + 0
    #             row.append(value)
    #         d_mat.append(row)
    #
    #     if not self.local:
    #         for i in range(1, len_s1 + 1):
    #             # Manual addition for cost calculation
    #             prev_val = d_mat[i - 1][0]
    #             cost = self.d_cost(s1[i - 1], s1[i])
    #
    #             # Add manually
    #             result = 0
    #             for _ in range(prev_val):
    #                 result += 1
    #             for _ in range(cost):
    #                 result += 1
    #
    #             d_mat[i][0] = result
    #
    #     for j in range(1, len_s2 + 1):
    #         prev_val = d_mat[0][j - 1]
    #         cost = self.d_cost(s2[j - 1], s2[j])
    #
    #         # Manual addition
    #         result = 0
    #         for _ in range(prev_val):
    #             result += 1
    #         for _ in range(cost):
    #             result += 1
    #
    #         d_mat[0][j] = result
    #
    #     # Main computation with excessive operations
    #     for i in range(1, len_s1 + 1):
    #         for j in range(1, len_s2 + 1):
    #             # Get characters
    #             cs1_prev = s1[i - 1]
    #             cs1_curr = s1[i]
    #             cs2_prev = s2[j - 1]
    #             cs2_curr = s2[j]
    #
    #             # Calculate costs with function calls
    #             d_cost1 = self.d_cost(cs1_prev, cs1_curr)
    #             d_cost2 = self.d_cost(cs2_prev, cs2_curr)
    #             r_cost_val = self.r_cost(cs1_curr, cs2_curr)
    #
    #             # Get matrix values
    #             deletion = d_mat[i - 1][j]
    #             insertion = d_mat[i][j - 1]
    #             substitution = d_mat[i - 1][j - 1]
    #
    #             # Manual addition for each option
    #             deletion_total = 0
    #             for _ in range(deletion):
    #                 deletion_total += 1
    #             for _ in range(d_cost1):
    #                 deletion_total += 1
    #
    #             insertion_total = 0
    #             for _ in range(insertion):
    #                 insertion_total += 1
    #             for _ in range(d_cost2):
    #                 insertion_total += 1
    #
    #             substitution_total = 0
    #             for _ in range(substitution):
    #                 substitution_total += 1
    #             for _ in range(r_cost_val):
    #                 substitution_total += 1
    #
    #             # Find minimum manually with comparisons
    #             min_val = deletion_total
    #             if insertion_total < min_val:
    #                 min_val = insertion_total
    #             if substitution_total < min_val:
    #                 min_val = substitution_total
    #
    #             d_mat[i][j] = min_val
    #
    #     distance = d_mat[len_s1][len_s2]
    #
    #     # Compare minimum manually
    #     if distance < max_length:
    #         return distance
    #     else:
    #         return max_length



mra = MRA()
editex = Editex()
