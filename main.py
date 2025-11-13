"""
Main entry point for the AI Phone Scheduler API.
This file imports the FastAPI app from the app module.
"""
from app.main import app

if __name__ == "__main__":
    import uvicorn
    from app.core.config import API_HOST, API_PORT, DEBUG, LOG_LEVEL
    
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG,
        log_level=LOG_LEVEL.lower()
    )