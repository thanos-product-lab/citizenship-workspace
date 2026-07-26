"""Cross-cutting primitives shared by every domain module.

`shared` owns the ORM `Base`, the session/`get_db` dependency, the transactional
unit-of-work, and the append-only infrastructure records (domain events, audit
entries, outbox). No domain module reaches into another's internals; the pieces
here are the sanctioned common ground.
"""
