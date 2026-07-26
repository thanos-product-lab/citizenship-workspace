"""The `applicants` module: the RouteProfile aggregate and route onboarding.

A RouteProfile holds the route-scope answers for one case. During onboarding a
single DRAFT version is edited in place; confirming (a later slice) mints an
immutable CONFIRMED version. Only confirmed versions may drive a support decision.
"""
