"""Local web API for the Legal.ai pipeline.

FastAPI app served by uvicorn inside the app container (see docker-compose.yml,
service `api`). Single-user, localhost-only by design: every user runs their own
instance with their own keys — there is no auth layer, and the compose file binds
the port to 127.0.0.1.
"""
