from fastapi import FastAPI
import sys
from inngest.fastapi import Inngest  # type: ignore
from functions.get_artist import get_artist

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application with Inngest integration.
    
    Returns:
        FastAPI: Configured FastAPI application instance
    """
    app = FastAPI()
    inngest = Inngest(app=app, functions=[get_artist])
    return app

app = create_app()
