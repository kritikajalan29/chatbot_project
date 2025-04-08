from inngest import inngest_function
import sqlite3
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

@inngest_function(name="Get Artist Details")
async def get_artist(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get artist details from the database.
    
    Args:
        event: Inngest event containing artist_name in data
        
    Returns:
        Dict containing artist details or error message
    """
    try:
        artist_name = event.data.get("artist_name", "")
        
        if not artist_name:
            logger.error("No artist name provided in event data")
            return {
                "status": "error",
                "message": "Artist name is required"
            }
        
        logger.info(f"Fetching details for artist: {artist_name}")
        
        conn = sqlite3.connect("chinook.db")
        cursor = conn.cursor()
        
        try:
            # Use case-insensitive search with wildcards
            cursor.execute(
                "SELECT * FROM artists WHERE LOWER(Name) LIKE LOWER(?)",
                (f"%{artist_name}%",)
            )
            result = cursor.fetchone()
            
            if not result:
                logger.warning(f"No artist found matching: {artist_name}")
                return {
                    "status": "not_found",
                    "message": f"No artist found matching '{artist_name}'"
                }
            
            # Convert result to dictionary for better readability
            columns = [description[0] for description in cursor.description]
            artist_details = dict(zip(columns, result))
            
            return {
                "status": "success",
                "artist_details": artist_details
            }
            
        finally:
            conn.close()
            
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        return {
            "status": "error",
            "message": f"Database error: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            "status": "error",
            "message": f"An unexpected error occurred: {str(e)}"
        }
