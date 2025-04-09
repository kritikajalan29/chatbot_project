from fastapi import FastAPI, Response
import os
import sys
import logging
from inngest.fastapi import Inngest  # type: ignore
from functions.get_artist import get_artist

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application with Inngest integration.
    
    Returns:
        FastAPI: Configured FastAPI application instance
    """
    app = FastAPI(
        title="Music Chatbot Inngest Worker",
        description="Background processing worker for the Music Chatbot application",
        version="1.0.0"
    )
    
    # Configure Inngest
    inngest_client = Inngest(
        app=app, 
        functions=[get_artist],
        logger=logger,
        event_key=os.environ.get("INNGEST_EVENT_KEY"),
        signing_key=os.environ.get("INNGEST_SIGNING_KEY")
    )
    
    # Add health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint for monitoring"""
        return {
            "status": "ok",
            "version": "1.0.0",
            "env": os.environ.get("FLASK_ENV", "production")
        }
    
    # Add favicon route to avoid 404s
    @app.get("/favicon.ico")
    async def favicon():
        """Return an empty response to favicon requests"""
        return Response(content="", media_type="image/x-icon")
    
    # Add root route
    @app.get("/")
    async def root():
        """Root endpoint provides basic info about the worker"""
        return {
            "name": "Music Chatbot Inngest Worker",
            "version": "1.0.0",
            "functions": ["get_artist"],
            "status": "running"
        }
    
    logger.info("FastAPI application configured with Inngest")
    return app

# Create and expose the app instance
app = create_app()

# Startup message when run directly
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting Inngest worker on port {port}")
    uvicorn.run("inngest_app:app", host="0.0.0.0", port=port, reload=True)
