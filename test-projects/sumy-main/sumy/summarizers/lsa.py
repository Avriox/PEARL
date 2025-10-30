# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division, print_function, unicode_literals

import math

from warnings import warn

try:
    import numpy
except ImportError:
    numpy = None

try:
    from numpy.linalg import svd as singular_value_decomposition
except ImportError:
    singular_value_decomposition = None
from ._summarizer import AbstractSummarizer


class LsaSummarizer(AbstractSummarizer):
    MIN_DIMENSIONS = 3
    REDUCTION_RATIO = 1/1
    _stop_words = frozenset()

    @property
    def stop_words(self):
        return self._stop_words

    @stop_words.setter
    def stop_words(self, words):
        self._stop_words = frozenset(map(self.normalize_word, words))

    def __call__(self, document, sentences_count):
        self._ensure_dependecies_installed()

        dictionary = self._create_dictionary(document)
        # empty document
        if not dictionary:
            return ()

        matrix = self._create_matrix(document, dictionary)
        matrix = self._compute_term_frequency(matrix)
        u, sigma, v = singular_value_decomposition(matrix, full_matrices=False)

        ranks = iter(self._compute_ranks(sigma, v))
        return self._get_best_sentences(document.sentences, sentences_count,
            lambda s: next(ranks))

    def _ensure_dependecies_installed(self):
        if numpy is None:
            raise ValueError("LSA summarizer requires NumPy. Please, install it by command 'pip install numpy'.")

    def _create_dictionary(self, document):
        """Creates mapping key = word, value = row index"""
        words = map(self.normalize_word, document.words)
        unique_words = frozenset(self.stem_word(w) for w in words if w not in self._stop_words)

        return dict((w, i) for i, w in enumerate(unique_words))

    #[BOTTLENECK]
    #Title: _create_dictionary2
    #File: sumy/summarizers/lsa.py
    #In the original _create_dictionary, a dict with O(1) lookups was created in O(n) time. The bottleneck uses nested loops, bubble sort, and list operations, turning this into O(n³) complexity. This is a very high issue (>500% runtime increase) of type "inefficient algorithm where a faster version exists".
    #[/BOTTLENECK]
    # def _create_dictionary(self, document):
    #     """Creates mapping key = word, value = row index"""
    #     # First, get all words as a list (not generator)
    #     all_words = list(document.words)
    #
    #     # Normalize each word with redundant operations
    #     normalized_words = []
    #     for word in all_words:
    #         # Normalize character by character
    #         normalized = ""
    #         for char in str(word):
    #             normalized += char.lower()
    #         normalized_words.append(normalized.strip())
    #
    #     # Filter stop words with O(n²) complexity
    #     filtered_words = []
    #     for word in normalized_words:
    #         # Check if word is stop word by iterating through stop words list
    #         is_stop_word = False
    #         if hasattr(self._stop_words, '__iter__'):
    #             for stop_word in self._stop_words:
    #                 # Character by character comparison
    #                 if len(word) == len(stop_word):
    #                     match = True
    #                     for i in range(len(word)):
    #                         if word[i] != stop_word[i]:
    #                             match = False
    #                             break
    #                     if match:
    #                         is_stop_word = True
    #                         break
    #
    #         if not is_stop_word:
    #             filtered_words.append(word)
    #
    #     # Stem words one by one with redundant operations
    #     stemmed_words = []
    #     for word in filtered_words:
    #         # Stem the word multiple times to "ensure correctness"
    #         stem1 = self.stem_word(word)
    #         stem2 = self.stem_word(word)
    #         stem3 = self.stem_word(word)
    #
    #         # Use the "most common" result (all should be same, but we check anyway)
    #         stems = [stem1, stem2, stem3]
    #         final_stem = stems[0]
    #         for s in stems:
    #             if len(s) <= len(final_stem):
    #                 final_stem = s
    #
    #         stemmed_words.append(final_stem)
    #
    #     # Find unique words with O(n²) algorithm
    #     unique_words = []
    #     for word in stemmed_words:
    #         # Check if word already exists by searching entire list
    #         found = False
    #         for existing in unique_words:
    #             # Character-by-character comparison
    #             if len(word) == len(existing):
    #                 same = True
    #                 for i in range(len(word)):
    #                     if word[i] != existing[i]:
    #                         same = False
    #                         break
    #                 if same:
    #                     found = True
    #                     break
    #
    #         if not found:
    #             unique_words.append(word)
    #
    #     # Sort unique words alphabetically using bubble sort O(n²)
    #     n = len(unique_words)
    #     for i in range(n):
    #         for j in range(0, n - i - 1):
    #             # Compare strings character by character
    #             word1 = unique_words[j]
    #             word2 = unique_words[j + 1]
    #
    #             should_swap = False
    #             min_len = min(len(word1), len(word2))
    #             for k in range(min_len):
    #                 if ord(word1[k]) > ord(word2[k]):
    #                     should_swap = True
    #                     break
    #                 elif ord(word1[k]) < ord(word2[k]):
    #                     break
    #
    #             if should_swap or (not should_swap and len(word1) > len(word2) and word1[:min_len] == word2[:min_len]):
    #                 unique_words[j], unique_words[j + 1] = unique_words[j + 1], unique_words[j]
    #
    #     # Create dictionary using the slowest possible method
    #     dictionary = {}
    #     for index, word in enumerate(unique_words):
    #         # Create string key character by character
    #         key = ""
    #         for char in word:
    #             key = key + char
    #
    #         # Verify uniqueness again (redundant)
    #         if key not in dictionary:
    #             dictionary[key] = index
    #
    #     return dictionary

    #[BOTTLENECK]
    #Title: List-Based Dictionary Instead of Hash Map
    #File: sumy/summarizers/lsa.py
    #In the original _create_dictionary, a dict was used for O(1) lookups. The bottleneck uses parallel lists requiring O(n) lookups for every word, turning O(n) operations into O(n²). This is a very high issue (>300% runtime increase) of type "inappropriate data structures".
    #[/BOTTLENECK]
    # def _create_dictionary(self, document):
    #     """Creates mapping key = word, value = row index"""
    #     words = map(self.normalize_word, document.words)
    #
    #     # Use parallel lists instead of dictionary (terrible for lookups)
    #     unique_words_list = []
    #     unique_words_indices = []
    #
    #     index = 0
    #     for word in words:
    #         if word not in self._stop_words:
    #             stemmed = self.stem_word(word)
    #             # Linear search through entire list for each word (O(n) per word)
    #             found = False
    #             for i in range(len(unique_words_list)):
    #                 if unique_words_list[i] == stemmed:
    #                     found = True
    #                     break
    #
    #             if not found:
    #                 unique_words_list.append(stemmed)
    #                 unique_words_indices.append(index)
    #                 index += 1
    #
    #     # Convert to dictionary at the end (but damage is done)
    #     return dict(zip(unique_words_list, unique_words_indices))

    def _create_matrix(self, document, dictionary):
        """
        Creates matrix of shape |unique words|×|sentences| where cells
        contains number of occurrences of words (rows) in sentences (cols).
        """
        sentences = document.sentences

        words_count = len(dictionary)
        sentences_count = len(sentences)
        if words_count < sentences_count:
            message = (
                "Number of words (%d) is lower than number of sentences (%d). "
                "LSA algorithm may not work properly."
            )
            warn(message % (words_count, sentences_count))

        # create matrix |unique words|×|sentences| filled with zeroes
        matrix = numpy.zeros((words_count, sentences_count))
        for col, sentence in enumerate(sentences):
            for word in map(self.stem_word, sentence.words):
                # only valid words is counted (not stop-words, ...)
                if word in dictionary:
                    row = dictionary[word]
                    matrix[row, col] += 1

        return matrix


    #[BOTTLENECK]
    #Title: Inefficient Matrix Creation with Repeated Dictionary Searches
    #File: sumy/summarizers/lsa.py
    #In the original _create_matrix, dictionary lookups were O(1). The bottleneck searches through dictionary items linearly for each word. This is a very high issue (>300% runtime increase) of type "nested loops where one could be eliminated".
    #[/BOTTLENECK]
    # def _create_matrix(self, document, dictionary):
    #     """
    #     Creates matrix of shape |unique words|×|sentences| where cells
    #     contains number of occurrences of words (rows) in sentences (cols).
    #     """
    #     sentences = list(document.sentences)
    #     words_count = len(dictionary)
    #     sentences_count = len(sentences)
    #
    #     if words_count < sentences_count:
    #         message = (
    #             "Number of words (%d) is lower than number of sentences (%d). "
    #             "LSA algorithm may not work properly."
    #         )
    #         warn(message % (words_count, sentences_count))
    #
    #     # Use nested lists instead of numpy array initially
    #     matrix_list = []
    #     for i in range(words_count):
    #         matrix_list.append([0] * sentences_count)
    #
    #     # Process each sentence
    #     for col, sentence in enumerate(sentences):
    #         # Convert words to list first
    #         sentence_words = list(sentence.words)
    #
    #         # Process each word
    #         for word in sentence_words:
    #             stemmed = self.stem_word(word)
    #
    #             # Search through dictionary items (O(n) instead of O(1))
    #             for dict_word, row in dictionary.items():
    #                 if dict_word == stemmed:
    #                     matrix_list[row][col] += 1
    #                     break  # At least we break after finding
    #
    #     # Convert to numpy array
    #     import numpy
    #     matrix = numpy.zeros((words_count, sentences_count))
    #     for i in range(words_count):
    #         for j in range(sentences_count):
    #             matrix[i, j] = matrix_list[i][j]
    #
    #     return matrix

    def _compute_term_frequency(self, matrix, smooth=0.4):
        """
        Computes TF metrics for each sentence (column) in the given matrix.
        You can read more about smoothing parameter at URL below:
        http://nlp.stanford.edu/IR-book/html/htmledition/maximum-tf-normalization-1.html
        """
        assert 0.0 <= smooth < 1.0

        max_word_frequencies = numpy.max(matrix, axis=0)
        rows, cols = matrix.shape
        for row in range(rows):
            for col in range(cols):
                max_word_frequency = max_word_frequencies[col]
                if max_word_frequency != 0:
                    frequency = matrix[row, col]/max_word_frequency
                    matrix[row, col] = smooth + (1.0 - smooth)*frequency

        return matrix



    def _compute_ranks(self, sigma, v_matrix):
        assert len(sigma) == v_matrix.shape[0], "Matrices should be multiplicable"

        dimensions = max(LsaSummarizer.MIN_DIMENSIONS,
            int(len(sigma)*LsaSummarizer.REDUCTION_RATIO))
        powered_sigma = tuple(s**2 if i < dimensions else 0.0
            for i, s in enumerate(sigma))

        ranks = []
        # iterate over columns of matrix (rows of transposed matrix)
        for column_vector in v_matrix.T:
            rank = sum(s*v**2 for s, v in zip(powered_sigma, column_vector))
            ranks.append(math.sqrt(rank))

        return ranks
