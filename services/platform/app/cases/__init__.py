"""The `cases` module: the ApplicationCase ownership + lifecycle aggregate.

A case is the ownership boundary (Domain §3.1): every case-scoped read or command
resolves user → membership → object-to-case before returning anything.
"""
