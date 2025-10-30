import time
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer as Summarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
import nltk


def main():
    # nltk.download('punkt_tab')
    LANGUAGE = "english"
    SENTENCES_COUNT = 1

    text = """
        Python (programming language)

        Article
        Talk

        Read
        Edit
        View history

    Tools

    Appearance
    Text

        Small
        Standard
        Large

    Width

        Standard
        Wide

    Color (beta)

        Automatic
        Light
        Dark

    From Wikipedia, the free encyclopedia
    Python
    Paradigm	Multi-paradigm: object-oriented,[1] procedural (imperative), functional, structured, reflective
    Designed by	Guido van Rossum
    Developer	Python Software Foundation
    First appeared	20 February 1991; 34 years ago[2]
    Stable release	
    3.13.7[3] Edit this on Wikidata / 14 August 2025; 33 days ago
    Preview release	
    3.14.0rc2 / 14 August 2025; 33 days ago
    Typing discipline	duck, dynamic, strong;[4] optional type annotations[a]
    OS	Cross-platform[b]
    License	Python Software Foundation License
    Filename extensions	.py, .pyw, .pyz,[11]
    .pyi, .pyc, .pyd
    Website	python.org
    Major implementations
    CPython, PyPy, MicroPython, CircuitPython, IronPython, Jython, Stackless Python
    Dialects
    Cython, RPython, Starlark[12]
    Influenced by
    ABC,[13] Ada,[14][failed verification] ALGOL 68,[15]
    APL,[16] C,[17] C++,[18] CLU,[19] Dylan,[20]
    Haskell,[21][16] Icon,[22] Lisp,[23]
    Modula-3,[15][18] Perl,[24] Standard ML[16]
    Influenced
    Apache Groovy, Boo, Cobra, CoffeeScript,[25] D, F#, GDScript, Go, JavaScript,[26][27] Julia,[28] Mojo,[29] Nim, Ring,[30] Ruby,[31] Swift,[32] V[33]

        Python Programming at Wikibooks

    Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation.[34]

    Python is dynamically type-checked and garbage-collected. It supports multiple programming paradigms, including structured (particularly procedural), object-oriented and functional programming.

    Guido van Rossum began working on Python in the late 1980s as a successor to the ABC programming language. Python 3.0, released in 2008, was a major revision not completely backward-compatible with earlier versions. Recent versions, such as Python 3.12, have added capabilites and keywords for typing (and more; e.g. increasing speed); helping with (optional) static typing.[35] Currently only versions in the 3.x series are supported.

    However, Python features regularly violate these principles and have received criticism for adding unnecessary language bloat.[67] Responses to these criticisms note that the Zen of Python is a guideline rather than a rule.[68] The addition of some new features had been controversial: Guido van Rossum resigned as Benevolent Dictator for Life after conflict about adding the assignment expression operator in Python 3.8 .[69][70]

    Nevertheless, rather than building all functionality into its core, Python was designed to be highly extensible via modules. This compact modularity has made it particularly popular as a means of adding programmable interfaces to existing applications. Van Rossum's vision of a small core language with a large standard library and easily extensible interpreter stemmed from his frustrations with ABC, which represented the opposite approach.[41]

    Python claims to strive for a simpler, less-cluttered syntax and grammar, while giving developers a choice in their coding methodology. In contrast to Perl's motto "there is more than one way to do it", Python advocates an approach where "there should be one – and preferably only one – obvious way to do it".[66] In practice, however, Python provides many ways to achieve a given goal. There are, for example, at least three ways to format a string literal, with no certainty as to which one a programmer should use.[71] Alex Martelli is a Fellow at the Python Software Foundation and Python book author; he wrote that "To describe something as 'clever' is not considered a compliment in the Python culture."[72]

    Python's developers usually try to avoid premature optimization; they also reject patches to non-critical parts of the CPython reference implementation that would offer marginal increases in speed at the cost of clarity.[73][failed verification] Execution speed can be improved by moving speed-critical functions to extension modules written in languages such as C, or by using a just-in-time compiler like PyPy. It is also possible to cross-compile to other languages; but this approach either fails to achieve the expected speed-up, since Python is a very dynamic language, or only a restricted subset of Python is compiled (with potential minor semantic changes).[74]

    Python's developers aim for the language to be fun to use. This goal is reflected in the name – a tribute to the British comedy group Monty Python[75] – and in playful approaches to some tutorials and reference materials. For instance, some code examples use the terms "spam" and "eggs" (in reference to a Monty Python sketch), rather than the typical terms "foo" and "bar".[76][77]

    A common neologism in the Python community is pythonic, which has a wide range of meanings related to program style: Pythonic code may use Python idioms well; be natural or show fluency in the language; or conform with Python's minimalist philosophy and emphasis on readability.[78]
    Syntax and semantics
    Main article: Python syntax and semantics
    Block of Python code showing sample source code
    An example of Python code and indentation
    C code featuring curly braces and semicolon
    Example of C# code with curly braces and semicolons

    Python is meant to be an easily readable language. Its formatting is visually uncluttered and often uses English keywords where other languages use punctuation. Unlike many other languages, it does not use curly brackets to delimit blocks, and semicolons after statements are allowed but rarely used. It has fewer syntactic exceptions and special cases than C or Pascal.[79]
    Indentation
    Main article: Python syntax and semantics § Indentation

    Python uses whitespace indentation, rather than curly brackets or keywords, to delimit blocks. An increase in indentation comes after certain statements; a decrease in indentation signifies the end of the current block.[80] Thus, the program's visual structure accurately represents its semantic structure.[81] This feature is sometimes termed the off-side rule. Some other languages use indentation this way; but in most, indentation has no semantic meaning. The recommended indent size is four spaces.[82]
    Statements and control flow

    Python's statements include the following:

        The assignment statement, using a single equals sign =
        The if statement, which conditionally executes a block of code, along with else and elif (a contraction of else if)
        The for statement, which iterates over an iterable object, capturing each element to a local variable for use by the attached block
        The while statement, which executes a block of code as long as boolean condition is true
        The try statement, which allows exceptions raised in its attached code block to be caught and handled by except clauses (or new syntax except* in Python 3.11 for exception groups[83]); the try statement also ensures that clean-up code in a finally block is always run regardless of how the block exits
        The raise statement, used to raise a specified exception or re-raise a caught exception
        The class statement, which executes a block of code and attaches its local namespace to a class, for use in object-oriented programming
        The def statement, which defines a function or method
        The with statement, which encloses a code block within a context manager, allowing resource-acquisition-is-initialization (RAII)-like behavior and replacing a common try/finally idiom[84] Examples of a context include acquiring a lock before some code is run, and then releasing the lock; or opening and then closing a file
        The break statement, which exits a loop
        The continue statement, which skips the rest of the current iteration and continues with the next
        The del statement, which removes a variable—deleting the reference from the name to the value, and producing an error if the variable is referred to before it is redefined [c]
        The pass statement, serving as a NOP (i.e., no operation), which is syntactically needed to create an empty code block
        The assert statement, used in debugging to check for conditions that should apply
        The yield statement, which returns a value from a generator function (and also an operator); used to implement coroutines
        The return statement, used to return a value from a function
        The import and from statements, used to import modules whose functions or variables can be used in the current program
        The match and case statements, analogous to a switch statement construct, which compares an expression against one or more cases as a control-flow measure

    The assignment statement (=) binds a name as a reference to a separate, dynamically allocated object. Variables may subsequently be rebound at any time to any object. In Python, a variable name is a generic reference holder without a fixed data type; however, it always refers to some object with a type. This is called dynamic typing—in contrast to statically-typed languages, where each variable may contain only a value of a certain type.

    Python does not support tail call optimization or first-class continuations; according to Van Rossum, the language never will.[85][86] However, better support for coroutine-like functionality is provided by extending Python's generators.[87] Before 2.5, generators were lazy iterators; data was passed unidirectionally out of the generator. From Python 2.5 on, it is possible to pass data back into a generator function; and from version 3.3, data can be passed through multiple stack levels.[88]
    Expressions

    Python's expressions include the following:

        Conditional expressions vs. if blocks
        The eval() vs. exec() built-in functions (in Python 2, exec is a statement); the former function is for expressions, while the latter is for statements

    A statement cannot be part of an expression; because of this restriction, expressions such as list and dict comprehensions (and lambda expressions) cannot contain statements. As a particular case, an assignment statement such as a = 1 cannot be part of the conditional expression of a conditional statement.
    Methods

   
    CPython is the reference implementation of Python. This implementation is written in C, meeting the C11 standard[127] since version 3.11. Older versions use the C89 standard with several select C99 features, but third-party extensions are not limited to older C versions—e.g., they can be implemented using C11 or C++.[128][129] CPython compiles Python programs into an intermediate bytecode,[130] which is then executed by a virtual machine.[131] CPython is distributed with a large standard library written in a combination of C and native Python.

    CPython is available for many platforms, including Windows and most modern Unix-like systems, including macOS (and Apple M1 Macs, since Python 3.9.1, using an experimental installer). Starting with Python 3.9, the Python installer intentionally fails to install on Windows 7 and 8;[132][133] Windows XP was supported until Python 3.5, with unofficial support for VMS.[134] Platform portability was one of Python's earliest priorities.[135] During development of Python 1 and 2, even OS/2 and Solaris were supported;[136] since that time, support has been dropped for many platforms.

    All current Python versions (since 3.7) support only operating systems that feature multithreading, by now supporting not nearly as many operating systems (dropping many outdated) than in the past.
    Other implementations

    All alternative implementations have at least slightly different semantics. For example, an alternative may include unordered dictionaries, in contrast to other current Python versions. As another example in the larger Python ecosystem, PyPy does not support the full C Python API. Alternative implementations include the following:

        PyPy is a fast, compliant interpreter of Python 2.7 and 3.10.[137][138] PyPy's just-in-time compiler often improves speed significantly relative to CPython, but PyPy does not support some libraries written in C.[139] PyPy offers support for the RISC-V instruction-set architecture.
        Codon is an implementation with an ahead-of-time (AOT) compiler, which compiles a statically-typed Python-like language whose "syntax and semantics are nearly identical to Python's, there are some notable differences"[140] For example, Codon uses 64-bit machine integers for speed, not arbitrarily as with Python; Codon developers claim that speedups over CPython are usually on the order of ten to a hundred times. Codon compiles to machine code (via LLVM) and supports native multithreading.[141] Codon can also compile to Python extension modules that can be imported and used from Python.
        MicroPython and CircuitPython are Python 3 variants that are optimized for microcontrollers, including the Lego Mindstorms EV3.[142]
        Pyston is a variant of the Python runtime that uses just-in-time compilation to speed up execution of Python programs.[143]
        Cinder is a performance-oriented fork of CPython 3.8 that features a number of optimizations, including bytecode inline caching, eager evaluation of coroutines, a method-at-a-time JIT, and an experimental bytecode compiler.[144]
        The Snek[145][146][147] embedded computing language "is Python-inspired, but it is not Python. It is possible to write Snek programs that run under a full Python system, but most Python programs will not run under Snek."[148] Snek is compatible with 8-bit AVR microcontrollers such as ATmega 328P-based Arduino, as well as larger microcontrollers that are compatible with MicroPython. Snek is an imperative language that (unlike Python) omits object-oriented programming. Snek supports only one numeric data type, which features 32-bit single precision (resembling JavaScript numbers, though smaller).

    Unsupported implementations

    Stackless Python is a significant fork of CPython that implements microthreads. This implementation uses the call stack differently, thus allowing massively concurrent programs. PyPy also offers a stackless version.[149]

    Just-in-time Python compilers have been developed, but are now unsupported:

        Google began a project named Unladen Swallow in 2009: this project aimed to speed up the Python interpreter five-fold by using LLVM, and improve multithreading capability for scaling to thousands of cores,[150] while typical implementations are limited by the global interpreter lock.
        Psyco is a discontinued just-in-time specializing compiler, which integrates with CPython and transforms bytecode to machine code at runtime. The emitted code is specialized for certain data types and is faster than standard Python code. Psyco does not support Python 2.7 or later.
        PyS60 was a Python 2 interpreter for Series 60 mobile phones, which was released by Nokia in 2005. The interpreter implemented many modules from Python's standard library, as well as additional modules for integration with the Symbian operating system. The Nokia N900 also supports Python through the GTK widget library, allowing programs to be written and run on the target device.[151]

    Cross-compilers to other languages

    There are several compilers/transpilers to high-level object languages; the source language is unrestricted Python, a subset of Python, or a language similar to Python:

        Brython,[152] Transcrypt,[153][154] and Pyjs compile Python to JavaScript. (The latest release of Pyjs was in 2012.)
        Cython compiles a superset of Python to C. The resulting code can be used with Python via direct C-level API calls into the Python interpreter.
        PyJL compiles/transpiles a subset of Python to "human-readable, maintainable, and high-performance Julia source code".[74] Despite the developers' performance claims, this is not possible for arbitrary Python code; that is, compiling to a faster language or machine code is known to be impossible in the general case. The semantics of Python might potentially be changed, but in many cases speedup is possible with few or no changes in the Python code. The faster Julia source code can then be used from Python or compiled to machine code.
        Nuitka compiles Python into C.[155] This compiler works with Python 3.4 to 3.12 (and 2.6 and 2.7) for Python's main supported platforms (and Windows 7 or even Windows XP) and for Android. The compiler developers claim full support for Python 3.10, partial support for Python 3.11 and 3.12, and experimental support for Python 3.13. Nuitka supports macOS including Apple Silicon-based versions. The compiler is free of cost, though it has commercial add-ons (e.g., for hiding source code).
        Numba is a JIT compiler that is used from Python; the compiler translates a subset of Python and NumPy code into fast machine code. This tool is enabled by adding a decorator to the relevant Python code.
        Pythran compiles a subset of Python 3 to C++ (C++11).[156]
        RPython can be compiled to C, and it is used to build the PyPy interpreter for Python.
        The Python → 11l → C++ transpiler[157] compiles a subset of Python 3 to C++ (C++17).
    Many alpha, beta, and release-candidates are also released as previews and for testing before final releases. Although there is a rough schedule for releases, they are often delayed if the code is not ready yet. Python's development team monitors the state of the code by running a large unit test suite during development.[176]

    The major academic conference on Python is PyCon. There are also special Python mentoring programs, such as PyLadies.
    API documentation generators

    Tools that can generate documentation for Python API include pydoc (available as part of the standard library); Sphinx; and Pdoc and its forks, Doxygen and Graphviz.[177]
    Naming

    Python's name is inspired by the British comedy group Monty Python, whom Python creator Guido van Rossum enjoyed while developing the language. Monty Python references appear frequently in Python code and culture;[178] for example, the metasyntactic variables often used in Python literature are spam and eggs, rather than the traditional foo and bar.[178][179] The official Python documentation also contains various references to Monty Python routines.[180][181] Python users are sometimes referred to as "Pythonistas".[182]

    The affix Py is often used when naming Python applications or libraries. Some examples include the following:

        Pygame, a binding of Simple DirectMedia Layer to Python (commonly used to create games);
        PyQt and PyGTK, which bind Qt and GTK to Python respectively;
        PyPy, a Python implementation originally written in Python;
        NumPy, a Python library for numerical processing.
        Jupyter, a notebook interface and associated project for interactive computing

    Popularity

    Since 2003, Python has consistently ranked in the top ten of the most popular programming languages in the TIOBE Programming Community Index; as of December 2022, Python was the most popular language.[38] Python was selected as Programming Language of the Year (for "the highest rise in ratings in a year") in 2007, 2010, 2018, 2020, 2021, and 2024 —the only language to have done so six times as of 2025[183]). In the TIOBE Index, monthly rankings are based on the volume of searches for programming languages on Google, Amazon, Wikipedia, Bing, and 20 other platforms. According to the accompanying graph, Python has shown a marked upward trend since the early 2000s, eventually passing more established languages such as C, C++, and Java. This trend can be attributed to Python's readable syntax, comprehensive standard library, and application in data science and machine learning fields.[184]
    TIOBE Index Chart showing Python's popularity compared to other programming languages

    Large organizations that use Python include Wikipedia, Google,[185] Yahoo!,[186] CERN,[187] NASA,[188] Facebook,[189] Amazon, Instagram,[190] Spotify,[191] and some smaller entities such as Industrial Light & Magic[192] and ITA.[193] The social news networking site Reddit was developed mostly in Python.[194] Organizations that partly use Python include Discord[195] and Baidu.[196]
    Types of use
    Further information: List of Python software
    Software that is powered by Python


    Python's development practices have also been emulated by other languages. For example, Python requires a document that describes the rationale and context for any language change; this document is known as a Python Enhancement Proposal or PEP. This practice is also used by the developers of Tcl,[240] Erlang,[241] and Swift.[242] 
        """

    parser = PlaintextParser.from_string(text, Tokenizer(LANGUAGE))
    stemmer = Stemmer(LANGUAGE)

    summarizer = Summarizer(stemmer)
    summarizer.stop_words = get_stop_words(LANGUAGE)

    start = time.perf_counter()

    sentences = [str(s) for s in summarizer(parser.document, SENTENCES_COUNT)]

    duration = time.perf_counter() - start

    print(f"Summarized {len(sentences)} sentences")
    for s in sentences:
        print("-", s)
    print(f"Duration: {duration:.3f} seconds")

if __name__ == "__main__":
    main()