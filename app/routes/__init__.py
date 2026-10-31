"""Route modules are imported explicitly by the application factory.

Keep this package initializer free of route imports so importing one route for
tests does not import every route and its unrelated service integrations.
"""
