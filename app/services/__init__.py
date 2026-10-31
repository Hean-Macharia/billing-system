"""Service modules are imported explicitly by routes and application code.

Avoid eager service imports here: they pull in unrelated providers and network
clients when a single service is needed in a test or route.
"""
