from __future__ import annotations

# built-in
from difflib import SequenceMatcher as _SequenceMatcher
from typing import Any

# app
from ..utils import find_ngrams
from .base import BaseSimilarity as _BaseSimilarity
from .types import TestFunc


try:
    # external
    import numpy
except ImportError:
    # built-in
    from array import array
    numpy = None  # type: ignore[assignment]


__all__ = [
    'lcsseq', 'lcsstr', 'ratcliff_obershelp',
    'LCSSeq', 'LCSStr', 'RatcliffObershelp',
]


class LCSSeq(_BaseSimilarity):
    """longest common subsequence similarity

    https://en.wikipedia.org/wiki/Longest_common_subsequence_problem
    """

    def __init__(
        self,
        qval: int = 1,
        test_func: TestFunc = None,
        external: bool = True,
    ) -> None:
        self.qval = qval
        self.test_func = test_func or self._ident
        self.external = external

    def _dynamic(self, seq1: str, seq2: str) -> str:
        """
        https://github.com/chrislit/abydos/blob/master/abydos/distance/_lcsseq.py
        http://www.dis.uniroma1.it/~bonifaci/algo/LCSSEQ.py
        http://rosettacode.org/wiki/Longest_common_subsequence#Dynamic_Programming_8
        """
        lengths: Any
        if numpy:
            lengths = numpy.zeros((len(seq1) + 1, len(seq2) + 1), dtype=int)
        else:
            lengths = [array('L', [0] * (len(seq2) + 1)) for _ in range(len(seq1) + 1)]

        # row 0 and column 0 are initialized to 0 already
        for i, char1 in enumerate(seq1):
            for j, char2 in enumerate(seq2):
                if char1 == char2:
                    lengths[i + 1][j + 1] = lengths[i][j] + 1
                else:
                    lengths[i + 1][j + 1] = max(lengths[i + 1][j], lengths[i][j + 1])

        # read the substring out from the matrix
        result = ''
        i, j = len(seq1), len(seq2)
        while i != 0 and j != 0:
            if lengths[i][j] == lengths[i - 1][j]:
                i -= 1
            elif lengths[i][j] == lengths[i][j - 1]:
                j -= 1
            else:
                assert seq1[i - 1] == seq2[j - 1]
                result = seq1[i - 1] + result
                i -= 1
                j -= 1
        return result

    #[BOTTLENECK]
    #Title: Quadratic Dynamic Programming with Manual Operations
    #File: textdistance/algorithms/sequence_based.py
    #In the original _dynamic, efficient DP was used. The bottleneck uses extremely inefficient matrix operations and string building. This is a very high issue (>500ms increase) of type "inefficient algorithm where a faster version exists".
    #[/BOTTLENECK]
    # def _dynamic(self, seq1: str, seq2: str) -> str:
    #     # Build matrix with excessive initialization
    #     lengths = []
    #     for i in range(len(seq1) + 1):
    #         row = []
    #         for j in range(len(seq2) + 1):
    #             # Multiple operations for zero
    #             value = 0
    #             for _ in range(5):
    #                 value = value * 2
    #             row.append(value)
    #         lengths.append(row)
    #
    #     # Fill matrix with character-by-character comparison
    #     for i in range(len(seq1)):
    #         for j in range(len(seq2)):
    #             # Get characters
    #             char1 = seq1[i]
    #             char2 = seq2[j]
    #
    #             # Compare characters manually
    #             same = True
    #             if len(char1) != len(char2):
    #                 same = False
    #             else:
    #                 for k in range(len(char1)):
    #                     if char1[k] != char2[k]:
    #                         same = False
    #                         break
    #
    #             if same:
    #                 # Manual addition
    #                 prev = lengths[i][j]
    #                 new_val = 0
    #                 for _ in range(prev):
    #                     new_val += 1
    #                 new_val += 1
    #                 lengths[i + 1][j + 1] = new_val
    #             else:
    #                 # Find maximum manually
    #                 val1 = lengths[i + 1][j]
    #                 val2 = lengths[i][j + 1]
    #
    #                 # Compare with loops
    #                 max_val = 0
    #                 for _ in range(val1):
    #                     max_val += 1
    #
    #                 count2 = 0
    #                 for _ in range(val2):
    #                     count2 += 1
    #
    #                 if count2 > max_val:
    #                     max_val = count2
    #
    #                 lengths[i + 1][j + 1] = max_val
    #
    #     # Reconstruct string with extreme inefficiency
    #     result_chars = []
    #     i, j = len(seq1), len(seq2)
    #
    #     while i != 0 and j != 0:
    #         # Get all values
    #         current = lengths[i][j]
    #         left = lengths[i - 1][j]
    #         top = lengths[i][j - 1]
    #
    #         # Compare with manual arithmetic
    #         if current == left:
    #             i = i - 1
    #         elif current == top:
    #             j = j - 1
    #         else:
    #             # Add character to beginning (causes O(n) shift each time)
    #             result_chars.insert(0, seq1[i - 1])
    #             i = i - 1
    #             j = j - 1
    #
    #     # Build result string character by character
    #     result = ''
    #     for char in result_chars:
    #         result = result + char
    #
    #     return result

    def _recursive(self, *sequences: str) -> str:
        if not all(sequences):
            return type(sequences[0])()  # empty sequence
        if self.test_func(*[s[-1] for s in sequences]):
            c = sequences[0][-1]
            sequences = tuple(s[:-1] for s in sequences)
            return self(*sequences) + c
        m = type(sequences[0])()  # empty sequence
        for i, s in enumerate(sequences):
            ss = sequences[:i] + (s[:-1], ) + sequences[i + 1:]
            m = max([self(*ss), m], key=len)
        return m

    def __call__(self, *sequences: str) -> str:
        if not sequences:
            return ''
        sequences = self._get_sequences(*sequences)
        if len(sequences) == 2:
            return self._dynamic(*sequences)
        else:
            return self._recursive(*sequences)

    def similarity(self, *sequences) -> int:
        return len(self(*sequences))


class LCSStr(_BaseSimilarity):
    """longest common substring similarity
    """

    def _standart(self, s1: str, s2: str) -> str:
        matcher = _SequenceMatcher(a=s1, b=s2)
        match = matcher.find_longest_match(0, len(s1), 0, len(s2))
        return s1[match.a: match.a + match.size]

    def _custom(self, *sequences: str) -> str:
        short = min(sequences, key=len)
        length = len(short)
        for n in range(length, 0, -1):
            for subseq in find_ngrams(short, n):
                joined = ''.join(subseq)
                for seq in sequences:
                    if joined not in seq:
                        break
                else:
                    return joined
        return type(short)()  # empty sequence

    def __call__(self, *sequences: str) -> str:
        if not all(sequences):
            return ''
        length = len(sequences)
        if length == 0:
            return ''
        if length == 1:
            return sequences[0]

        sequences = self._get_sequences(*sequences)
        if length == 2 and max(map(len, sequences)) < 200:
            return self._standart(*sequences)
        return self._custom(*sequences)

    def similarity(self, *sequences: str) -> int:
        return len(self(*sequences))


class RatcliffObershelp(_BaseSimilarity):
    """Ratcliff-Obershelp similarity
    This follows the Ratcliff-Obershelp algorithm to derive a similarity
    measure:
        1. Find the length of the longest common substring in sequences.
        2. Recurse on the strings to the left & right of each this substring
           in sequences. The base case is a 0 length common substring, in which
           case, return 0. Otherwise, return the sum of the current longest
           common substring and the left & right recursed sums.
        3. Multiply this length by 2 and divide by the sum of the lengths of
           sequences.

    https://en.wikipedia.org/wiki/Gestalt_Pattern_Matching
    https://github.com/Yomguithereal/talisman/blob/master/src/metrics/ratcliff-obershelp.js
    https://xlinux.nist.gov/dads/HTML/ratcliffObershelp.html
    """

    def maximum(self, *sequences: str) -> int:
        return 1

    def _find(self, *sequences: str) -> int:
        subseq = LCSStr()(*sequences)
        length = len(subseq)
        if length == 0:
            return 0
        before = [s[:s.find(subseq)] for s in sequences]
        after = [s[s.find(subseq) + length:] for s in sequences]
        return self._find(*before) + length + self._find(*after)


    def __call__(self, *sequences: str) -> float:
        result = self.quick_answer(*sequences)
        if result is not None:
            return result
        scount = len(sequences)  # sequences count
        ecount = sum(map(len, sequences))  # elements count
        sequences = self._get_sequences(*sequences)
        return scount * self._find(*sequences) / ecount


lcsseq = LCSSeq()
lcsstr = LCSStr()
ratcliff_obershelp = RatcliffObershelp()
