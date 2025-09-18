import time
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer as Summarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
import nltk


if __name__ == "__main__":
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

Python consistently ranks as one of the most popular programming languages, and it has gained widespread use in the machine learning community.[36][37][38][39] It is widely taught as an introductory programming language.[40]
History
Main article: History of Python
The designer of Python, Guido van Rossum, at PyCon US 2024

Python was conceived in the late 1980s[41] by Guido van Rossum at Centrum Wiskunde & Informatica (CWI) in the Netherlands (he first released it in 1991 as Python 0.9.0.[42]); it was conceived as a successor to the ABC programming language, which was inspired by SETL,[43] capable of exception handling and interfacing with the Amoeba operating system.[13] Python implementation began in December, 1989.[44] Van Rossum assumed sole responsibility for the project, as the lead developer, until 12 July 2018, when he announced his "permanent vacation" from responsibilities as Python's "benevolent dictator for life" (BDFL); this title was bestowed on him by the Python community to reflect his long-term commitment as the project's chief decision-maker.[45] (He has since come out of retirement and is self-titled "BDFL-emeritus".) In January 2019, active Python core developers elected a five-member Steering Council to lead the project.[46][47]

The name Python derives from the British comedy series Monty Python's Flying Circus.[48] (See § Naming.)

Python 2.0 was released on 16 October 2000, with many major new features such as list comprehensions, cycle-detecting garbage collection, reference counting, and Unicode support.[49] Python 2.7's end-of-life was initially set for 2015, and then postponed to 2020 out of concern that a large body of existing code could not easily be forward-ported to Python 3.[50][51] It no longer receives security patches or updates.[52][53] While Python 2.7 and older versions are officially unsupported, a different unofficial Python implementation, PyPy, continues to support Python 2, i.e., "2.7.18+" (plus 3.10), with the plus signifying (at least some) "backported security updates".[54]

Python 3.0 was released on 3 December 2008, was a major revision not completely backward-compatible with earlier versions, with some new semantics and changed syntax. Python 2.7.18, released in 2020, was the last release of Python 2.[55] Several releases in the Python 3.x series have added new syntax to the language, and made a few (considered very minor) backwards-incompatible changes.

As of 14 August 2025, Python 3.13 is the latest stable release and Python 3.9 is the oldest supported release.[56] Releases receive two years of full support followed by three years of security support.
Design philosophy and features

Python is a multi-paradigm programming language. Object-oriented programming and structured programming are fully supported, and many of their features support functional programming and aspect-oriented programming – including metaprogramming[57] and metaobjects.[58] Many other paradigms are supported via extensions, including design by contract[59][60] and logic programming.[61] Python is often referred to as a 'glue language'[62] because it is purposely designed to be able to integrate components written in other languages.

Python uses dynamic typing and a combination of reference counting and a cycle-detecting garbage collector for memory management.[63] It uses dynamic name resolution (late binding), which binds method and variable names during program execution.

Python's design offers some support for functional programming in the "Lisp tradition". It has filter, map, and reduce functions; list comprehensions, dictionaries, sets, and generator expressions.[64] The standard library has two modules (itertools and functools) that implement functional tools borrowed from Haskell and Standard ML.[65]

Python's core philosophy is summarized in the Zen of Python (PEP 20), which includes aphorisms such as these:[66]

    Beautiful is better than ugly.
    Explicit is better than implicit.
    Simple is better than complex.
    Complex is better than complicated.
    Readability counts.

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

    The +, -, and * operators for mathematical addition, subtraction, and multiplication are similar to other languages, but the behavior of division differs. There are two types of division in Python: floor division (or integer division) //, and floating-point division /.[89] Python uses the ** operator for exponentiation.
    Python uses the + operator for string concatenation. The language uses the * operator for duplicating a string a specified number of times.
    The @ infix operator is intended to be used by libraries such as NumPy for matrix multiplication.[90][91]
    The syntax :=, called the "walrus operator", was introduced in Python 3.8. This operator assigns values to variables as part of a larger expression.[92]
    In Python, == compares two objects by value. Python's is operator may be used to compare object identities (i.e., comparison by reference), and comparisons may be chained—for example, a <= b <= c.
    Python uses and, or, and not as Boolean operators.
    Python has a type of expression called a list comprehension, and a more general expression called a generator expression.[64]
    Anonymous functions are implemented using lambda expressions; however, there may be only one expression in each body.
    Conditional expressions are written as x if c else y.[93] (This is different in operand order from the c ? x : y operator common to many other languages.)
    Python makes a distinction between lists and tuples. Lists are written as [1, 2, 3], are mutable, and cannot be used as the keys of dictionaries (since dictionary keys must be immutable in Python). Tuples, written as (1, 2, 3), are immutable and thus can be used as the keys of dictionaries, provided that all of the tuple's elements are immutable. The + operator can be used to concatenate two tuples, which does not directly modify their contents, but produces a new tuple containing the elements of both. For example, given the variable t initially equal to (1, 2, 3), executing t = t + (4, 5) first evaluates t + (4, 5), which yields (1, 2, 3, 4, 5); this result is then assigned back to t—thereby effectively "modifying the contents" of t while conforming to the immutable nature of tuple objects. Parentheses are optional for tuples in unambiguous contexts.[94]
    Python features sequence unpacking where multiple expressions, each evaluating to something assignable (e.g., a variable or a writable property) are associated just as in forming tuple literal; as a whole, the results are then put on the left-hand side of the equal sign in an assignment statement. This statement expects an iterable object on the right-hand side of the equal sign to produce the same number of values as the writable expressions on the left-hand side; while iterating, the statement assigns each of the values produced on the right to the corresponding expression on the left.[95]
    Python has a "string format" operator % that functions analogously to printf format strings in the C language—e.g. "spam=%s eggs=%d" % ("blah", 2) evaluates to "spam=blah eggs=2". In Python 2.6+ and 3+, this operator was supplemented by the format() method of the str class, e.g., "spam={0} eggs={1}".format("blah", 2). Python 3.6 added "f-strings": spam = "blah"; eggs = 2; f'spam={spam} eggs={eggs}'.[96]
    Strings in Python can be concatenated by "adding" them (using the same operator as for adding integers and floats); e.g., "spam" + "eggs" returns "spameggs". If strings contain numbers, they are concatenated as strings rather than as integers, e.g. "2" + "2" returns "22".
    Python supports string literals in several ways:
        Delimited by single or double quotation marks; single and double quotation marks have equivalent functionality (unlike in Unix shells, Perl, and Perl-influenced languages). Both marks use the backslash (\) as an escape character. String interpolation became available in Python 3.6 as "formatted string literals".[96]
        Triple-quoted, i.e., starting and ending with three single or double quotation marks; this may span multiple lines and function like here documents in shells, Perl, and Ruby.
        Raw string varieties, denoted by prefixing the string literal with r. Escape sequences are not interpreted; hence raw strings are useful where literal backslashes are common, such as in regular expressions and Windows-style paths. (Compare "@-quoting" in C#.)
    Python has array index and array slicing expressions in lists, which are written as a[key], a[start:stop] or a[start:stop:step]. Indexes are zero-based, and negative indexes are relative to the end. Slices take elements from the start index up to, but not including, the stop index. The (optional) third slice parameter, called step or stride, allows elements to be skipped or reversed. Slice indexes may be omitted—for example, a[:] returns a copy of the entire list. Each element of a slice is a shallow copy.

In Python, a distinction between expressions and statements is rigidly enforced, in contrast to languages such as Common Lisp, Scheme, or Ruby. This distinction leads to duplicating some functionality, for example:

    List comprehensions vs. for-loops
    Conditional expressions vs. if blocks
    The eval() vs. exec() built-in functions (in Python 2, exec is a statement); the former function is for expressions, while the latter is for statements

A statement cannot be part of an expression; because of this restriction, expressions such as list and dict comprehensions (and lambda expressions) cannot contain statements. As a particular case, an assignment statement such as a = 1 cannot be part of the conditional expression of a conditional statement.
Methods

Methods of objects are functions attached to the object's class; the syntax for normal methods and functions, instance.method(argument), is syntactic sugar for Class.method(instance, argument). Python methods have an explicit self parameter to access instance data, in contrast to the implicit self (or this) parameter in some object-oriented programming languages (e.g., C++, Java, Objective-C, Ruby).[97] Python also provides methods, often called dunder methods (because their names begin and end with double underscores); these methods allow user-defined classes to modify how they are handled by native operations including length, comparison, arithmetic, and type conversion.[98]
Typing
The standard type hierarchy in Python 3

Python uses duck typing, and it has typed objects but untyped variable names. Type constraints are not checked at definition time; rather, operations on an object may fail at usage time, indicating that the object is not of an appropriate type. Despite being dynamically typed, Python is strongly typed, forbidding operations that are poorly defined (e.g., adding a number and a string) rather than quietly attempting to interpret them.

Python allows programmers to define their own types using classes, most often for object-oriented programming. New instances of classes are constructed by calling the class, for example, SpamClass() or EggsClass()); the classes are instances of the metaclass type (which is an instance of itself), thereby allowing metaprogramming and reflection.

Before version 3.0, Python had two kinds of classes, both using the same syntax: old-style and new-style.[99] Current Python versions support the semantics of only the new style.

Python supports optional type annotations.[5][100] These annotations are not enforced by the language, but may be used by external tools such as mypy to catch errors. Python includes a module typing including several type names for type annotations.[101][102] Mypy also supports a Python compiler called mypyc, which leverages type annotations for optimization.[103]
Summary of Python 3's built-in types Type 	Mutability 	Description 	Syntax examples
bool 	immutable 	Boolean value 	True
False
bytearray 	mutable 	Sequence of bytes 	bytearray(b'Some ASCII')
bytearray(b"Some ASCII")
bytearray([119, 105, 107, 105])
bytes 	immutable 	Sequence of bytes 	b'Some ASCII'
b"Some ASCII"
bytes([119, 105, 107, 105])
complex 	immutable 	Complex number with real and imaginary parts 	3+2.7j
3 + 2.7j
dict 	mutable 	Associative array (or dictionary) of key and value pairs; can contain mixed types (keys and values); keys must be a hashable type 	{'key1': 1.0, 3: False}
{}
types.EllipsisType 	immutable 	An ellipsis placeholder to be used as an index in NumPy arrays 	...
Ellipsis
float 	immutable 	Double-precision floating-point number. The precision is machine-dependent, but in practice it is generally implemented as a 64-bit IEEE 754 number with 53 bits of precision.[104] 	

1.33333
frozenset 	immutable 	Unordered set, contains no duplicates; can contain mixed types, if hashable 	frozenset([4.0, 'string', True])
int 	immutable 	Integer of unlimited magnitude[105] 	42
list 	mutable 	List, can contain mixed types 	[4.0, 'string', True]
[]
types.NoneType 	immutable 	An object representing the absence of a value, often called null in other languages 	None
types.NotImplementedType 	immutable 	A placeholder that can be returned from overloaded operators to indicate unsupported operand types. 	NotImplemented
range 	immutable 	An immutable sequence of numbers, commonly used for iterating a specific number of times in for loops[106] 	range(−1, 10)
range(10, −5, −2)
set 	mutable 	Unordered set, contains no duplicates; can contain mixed types, if hashable 	{4.0, 'string', True}
set()
str 	immutable 	A character string: sequence of Unicode codepoints 	'Wikipedia'
"Wikipedia"

'spanning
multiple
lines'

tuple 	immutable 	Tuple, can contain mixed types 	(4.0, 'string', True)
('single element',)
()
Arithmetic operations

Python includes conventional symbols for arithmetic operators (+, -, *, /), the floor-division operator //, and the modulo operator %. (With the modulo operator, a remainder can be negative, e.g., 4 % -3 == -2.) Python also offers the ** symbol for exponentiation, e.g. 5**3 == 125 and 9**0.5 == 3.0; it also offers the matrix‑multiplication operator @ .[107] These operators work as in traditional mathematics; with the same precedence rules, the infix operators + and - can also be unary, to represent positive and negative numbers respectively.

Division between integers produces floating-point results. The behavior of division has changed significantly over time:[108]

    The current version of Python (i.e., since 3.0) changed the / operator to always represent floating-point division, e.g., 5/2 == 2.5.
    The floor division // operator was introduced. Thus 7//3 == 2, -7//3 == -3, 7.5//3 == 2.0, and -7.5//3 == -3.0. For outdated Python 2.7 adding the from __future__ import division statement causes a module in Python 2.7 to use Python 3.0 rules for division instead (see above).

In Python terms, the / operator represents true division (or simply division), while the // operator represents floor division. Before version 3.0, the / operator represents classic division.[108]

Rounding towards negative infinity, though a different method than in most languages, adds consistency to Python. For instance, this rounding implies that the equation (a + b)//b == a//b + 1 is always true. The rounding also implies that the equation b*(a//b) + a%b == a is valid for both positive and negative values of a. As expected, the result of a%b lies in the half-open interval [0, b), where b is a positive integer; however, maintaining the validity of the equation requires that the result must lie in the interval (b, 0] when b is negative.[109]

Python provides a round function for rounding a float to the nearest integer. For tie-breaking, Python 3 uses the round to even method: round(1.5) and round(2.5) both produce 2.[110] Python versions before 3 used the round-away-from-zero method: round(0.5) is 1.0, and round(-0.5) is −1.0.[111]

Python allows Boolean expressions that contain multiple equality relations to be consistent with general usage in mathematics. For example, the expression a < b < c tests whether a is less than b and b is less than c.[112] C-derived languages interpret this expression differently: in C, the expression would first evaluate a < b, resulting in 0 or 1, and that result would then be compared with c.[113]

Python uses arbitrary-precision arithmetic for all integer operations. The Decimal type/class in the decimal module provides decimal floating-point numbers to a pre-defined arbitrary precision with several rounding modes.[114] The Fraction class in the fractions module provides arbitrary precision for rational numbers.[115]

Due to Python's extensive mathematics library and the third-party library NumPy, the language is frequently used for scientific scripting in tasks such as numerical data processing and manipulation.[116][117]
Function syntax

Functions are created in Python by using the def keyword. A function is defined similarly to how it is called, by first providing the function name and then the required parameters. Here is an example of a function that prints its inputs:

def printer(input1: str, input2: str = "already there") -> None:
    print(input1)
    print(input2)
    
printer("hello")
    
# Example output:
# hello
# already there

To assign a default value to a function parameter in case no actual value is provided at run time, variable-definition syntax can be used inside the function header.
Code examples

"Hello, World!" program:

print('Hello, world!')

Program to calculate the factorial of a positive integer:

text: str = input('Type a number, and its factorial will be printed: ')
n: int = int(text)

if n < 0:
    raise ValueError('You must enter a non-negative integer')

factorial: int = 1
for i in range(2, n + 1):
    factorial *= i

print(factorial)

Libraries

Python's large standard library[118] is commonly cited as one of its greatest strengths. For Internet-facing applications, many standard formats and protocols such as MIME and HTTP are supported. The language includes modules for creating graphical user interfaces, connecting to relational databases, generating pseudorandom numbers, arithmetic with arbitrary-precision decimals,[114] manipulating regular expressions, and unit testing.

Some parts of the standard library are covered by specifications—for example, the Web Server Gateway Interface (WSGI) implementation wsgiref follows PEP 333[119]—but most parts are specified by their code, internal documentation, and test suites. However, because most of the standard library is cross-platform Python code, only a few modules must be altered or rewritten for variant implementations.

As of 13 March 2025, the Python Package Index (PyPI), the official repository for third-party Python software, contains over 614,339[120] packages. These have a wide range of functionality, including the following:

    Automation
    Data analytics
    Databases
    Documentation
    Graphical user interfaces
    Image processing
    Machine learning
    Mobile apps
    Multimedia
    Computer networking
    Scientific computing
    System administration
    Test frameworks
    Text processing
    Web frameworks
    Web scraping

Development environments
See also: Comparison of integrated development environments § Python

Most[which?] Python implementations (including CPython) include a read–eval–print loop (REPL); this permits the environment to function as a command line interpreter, with which users enter statements sequentially and receive results immediately.[121]

Python is also bundled with an integrated development environment (IDE) called IDLE,[122] which is oriented toward beginners.[citation needed]

Other shells, including IDLE and IPython, add additional capabilities such as improved auto-completion, session-state retention, and syntax highlighting.[122][123]

Standard desktop IDEs include PyCharm, Spyder, and Visual Studio Code;[citation needed] there are also web browser-based IDEs, such as the following environments:

    Jupyter Notebooks, an open-source interactive computing platform;[124]
    PythonAnywhere, a browser-based IDE and hosting environment; and
    Canopy, a commercial IDE from Enthought that emphasizes scientific computing.[125][126]

Implementations
See also: List of Python software § Python implementations
Reference implementation

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

There are also specialized compilers:

    MyHDL is a Python-based hardware description language (HDL) that converts MyHDL code to Verilog or VHDL code.

Some older projects existed, as well as compilers not designed for use with Python 3.x and related syntax:

    Google's Grumpy transpiles Python 2 to Go.[158][159][160] The latest release was in 2017.
    IronPython allows running Python 2.7 programs with the .NET Common Language Runtime.[161] An alpha version (released in 2021), is available for "Python 3.4, although features and behaviors from later versions may be included."[162]
    Jython compiles Python 2.7 to Java bytecode, allowing the use of Java libraries from a Python program.[163]
    Pyrex (last released in 2010) and Shed Skin (last released in 2013) compile to C and C++ respectively.

Performance

A performance comparison among various Python implementations, using a non-numerical (combinatorial) workload, was presented at EuroSciPy '13.[164] In addition, Python's performance relative to other programming languages is benchmarked by The Computer Language Benchmarks Game.[165]

There are several approaches to optimizing Python performance, given the inherent slowness of an interpreted language. These approaches include the following strategies or tools:

    Just-in-time compilation: Dynamically compiling Python code just before it is executed. This technique is used in libraries such as Numba and PyPy.
    Static compilation: Python code is compiled into machine code sometime before execution. An example of this approach is Cython, which compiles Python into C.
    Concurrency and parallelism: Multiple tasks can be run simultaneously. Python contains modules such as `multiprocessing` to support this form of parallelism. Moreover, this approach helps to overcome limitations of the Global Interpreter Lock (GIL) in CPU tasks.
    Efficient data structures: Performance can also be improved by using data types such as Set for membership tests, or deque from collections for queue operations.

Language Development

Python's development is conducted largely through the Python Enhancement Proposal (PEP) process; this process is the primary mechanism for proposing major new features, collecting community input on issues, and documenting Python design decisions.[166] Python coding style is covered in PEP 8.[167] Outstanding PEPs are reviewed and commented on by the Python community and the steering council.[166]

Enhancement of the language corresponds with development of the CPython reference implementation. The mailing list python-dev is the primary forum for the language's development. Specific issues were originally discussed in the Roundup bug tracker hosted by the foundation.[168] In 2022, all issues and discussions were migrated to GitHub.[169] Development originally took place on a self-hosted source-code repository running Mercurial, until Python moved to GitHub in January 2017.[170]

CPython's public releases have three types, distinguished by which part of the version number is incremented:

    Backward-incompatible versions, where code is expected to break and must be manually ported. The first part of the version number is incremented. These releases happen infrequently—version 3.0 was released 8 years after 2.0. According to Guido van Rossum, a version 4.0 will probably never exist.[171]
    Major or "feature" releases are largely compatible with the previous version but introduce new features. The second part of the version number is incremented. Starting with Python 3.9, these releases are expected to occur annually.[172][173] Each major version is supported by bug fixes for several years after its release.[174]
    Bug fix releases,[175] which introduce no new features, occur approximately every three months; these releases are made when a sufficient number of bugs have been fixed upstream since the last release. Security vulnerabilities are also patched in these releases. The third and final part of the version number is incremented.[175]

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

Python has many uses, including the following:

    Scripting for web applications
    Scientific computing
    Artificial intelligence and machine learning projects
    Graphical user interfaces and desktop environments
    Embedded scripting in software and hardware products
    Operating systems
    Information security

Python can serve as a scripting language for web applications, e.g., via the mod_wsgi module for the Apache web server.[197] With Web Server Gateway Interface, a standard API has evolved to facilitate these applications. Web frameworks such as Django, Pylons, Pyramid, TurboGears, web2py, Tornado, Flask, Bottle, and Zope support developers in the design and maintenance of complex applications. Pyjs and IronPython can be used to develop the client-side of Ajax-based applications. SQLAlchemy can be used as a data mapper to a relational database. Twisted is a framework to program communication between computers; this framework is used by Dropbox, for example.

Libraries such as NumPy, SciPy and Matplotlib allow the effective use of Python in scientific computing,[198][199] with specialized libraries such as Biopython and Astropy providing domain-specific functionality. SageMath is a computer algebra system with a notebook interface that is programmable in Python; the SageMath library covers many aspects of mathematics, including algebra, combinatorics, numerical mathematics, number theory, and calculus.[200] OpenCV has Python bindings with a rich set of features for computer vision and image processing.[201]

Python is commonly used in artificial-intelligence and machine-learning projects, with support from libraries such as TensorFlow, Keras, Pytorch, scikit-learn and ProbLog (a logic language).[202][203][204][205][206] As a scripting language with a modular architecture, simple syntax, and rich text processing tools, Python is often used for natural language processing.[207]

The combination of Python and Prolog has proven useful for AI applications, with Prolog providing knowledge representation and reasoning capabilities. The Janus system, in particular, exploits similarities between these two languages, in part because of their dynamic typing and their simple, recursive data structures. This combination is typically applied natural language processing, visual query answering, geospatial reasoning, and handling semantic web data.[208][209] The Natlog system, implemented in Python, uses Definite Clause Grammars (DCGs) to create prompts for two types of generators: text-to-text generators such as GPT3, and text-to-image generators such as DALL-E or Stable Diffusion.[210]

Python can be used for graphical user interfaces (GUIs), by using libraries such as Tkinter.[211] Similarly, for the One Laptop per Child XO computer, most of the Sugar desktop environment is written in Python (as of 2008).[212]

Python is embedded in many software products (and some hardware products) as a scripting language. These products include the following:

    finite element method software such as Abaqus,
    3D parametric modelers such as FreeCAD,
    3D animation packages such as 3ds Max, Blender, Cinema 4D, Lightwave, Houdini, Maya, modo, MotionBuilder, Softimage,
    the visual effects compositor Nuke,
    2D imaging programs such as GIMP,[213] Inkscape, Scribus and Paint Shop Pro,[214] and
    musical notation programs such as scorewriter and capella.

Similarly, GNU Debugger uses Python as a pretty printer to show complex structures such as C++ containers. Esri promotes Python as the best choice for writing scripts in ArcGIS.[215] Python has also been used in several video games,[216][217] and it has been adopted as first of the three programming languages available in Google App Engine (the other two being Java and Go).[218] LibreOffice includes Python, and its developers plan to replace Java with Python; LibreOffice's Python Scripting Provider is a core feature[219] since version 4.0 (from 7 February 2013).

Among hardware products, the Raspberry Pi single-board computer project has adopted Python as its main user-programming language.

Many operating systems include Python as a standard component. Python ships with most Linux distributions,[220] AmigaOS 4 (using Python 2.7), FreeBSD (as a package), NetBSD, and OpenBSD (as a package); it can be used from the command line (terminal). Many Linux distributions use installers written in Python: Ubuntu uses the Ubiquity installer, while Red Hat Linux and Fedora Linux use the Anaconda installer. Gentoo Linux uses Python in its package management system, Portage.[221]

Python is used extensively in the information security industry, including in exploit development.[222][223]
Limitations

    The energy usage of Python is much worse than C by a factor of 75.88.[224]
    Python lacks do while loops.[225]
    The throughput of Python is worse than C by a factor of 71.9.[224]
    The average memory usage of Python is worse than C by a factor of 2.4.[224]
    Creating an executable with Python requires bundling the entire Python interpreter into the executable, which causes binary sizes of small executable to be massive.[226]
    Significant whitespace causes Python scripts to be difficult to minify. The most compact minification can transform each indent level into a tab.[227] However, this always takes up at least as much or more than braces.

Languages influenced by Python

Python's design and philosophy have influenced many other programming languages:

    Boo uses indentation, a similar syntax, and a similar object model.[228]
    Cobra uses indentation and a similar syntax; its Acknowledgements document lists Python first among influencing languages.[229]
    CoffeeScript, a programming language that cross-compiles to JavaScript, has a Python-inspired syntax.
    ECMAScript–JavaScript borrowed iterators and generators from Python.[230]
    GDScript, a Python-like scripting language that is built in to the Godot game engine.[231]
    Go is designed for "speed of working in a dynamic language like Python";[232] Go shares Python's syntax for slicing arrays.
    Groovy was motivated by a desire to incorporate the Python design philosophy into Java.[233]
    Julia was designed to be "as usable for general programming as Python".[28]
    Mojo is a non-strict[29][234] superset of Python (e.g., omitting classes, and adding struct).[235]
    Nim uses indentation and a similar syntax.[236]
    Ruby's creator, Yukihiro Matsumoto, said that "I wanted a scripting language that was more powerful than Perl, and more object-oriented than Python. That's why I decided to design my own language."[237]
    Swift, a programming language developed by Apple, has some Python-inspired syntax.[238]
    Kotlin blends Python and Java features, which minimizes boilerplate code and enhances developer efficiency.[239]

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
