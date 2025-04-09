from inngest import inngest_function
import sqlite3
import logging
import requests
import os
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Load environment variables or use defaults
FLASK_WEBHOOK_URL = os.environ.get("FLASK_WEBHOOK_URL", "http://localhost:5000/webhook/artist-result")

@inngest_function(name="Get Artist Details")
async def get_artist(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get artist details from the database.
    This function retrieves detailed information about an artist and their albums.
    
    Args:
        event: Inngest event containing artist_name in data
        
    Returns:
        Dict containing artist details or error message
    """
    try:
        artist_name = event.data.get("artist_name", "")
        
        if not artist_name:
            logger.error("No artist name provided in event data")
            response_data = {
                "status": "error",
                "message": "Artist name is required",
                "artist_name": artist_name
            }
            # Send result back to Flask app
            try:
                requests.post(FLASK_WEBHOOK_URL, json=response_data, timeout=5)
            except Exception as webhook_error:
                logger.error(f"Failed to send webhook: {str(webhook_error)}")
            return response_data
        
        logger.info(f"Fetching details for artist: {artist_name}")
        
        conn = sqlite3.connect("chinook.db")
        conn.row_factory = sqlite3.Row  # Use Row to get column names
        cursor = conn.cursor()
        
        try:
            # First try exact match
            cursor.execute(
                "SELECT ArtistId, Name FROM Artist WHERE LOWER(Name) = LOWER(?)",
                (artist_name.lower(),)
            )
            artist_result = cursor.fetchone()
            
            # If no exact match, try partial match
            if not artist_result:
                cursor.execute(
                    "SELECT ArtistId, Name FROM Artist WHERE LOWER(Name) LIKE LOWER(?)",
                    (f"%{artist_name.lower()}%",)
                )
                artist_result = cursor.fetchone()
            
            if not artist_result:
                logger.warning(f"No artist found matching: {artist_name}")
                response_data = {
                    "status": "not_found",
                    "message": f"No artist found matching '{artist_name}'",
                    "artist_name": artist_name
                }
                # Send result back to Flask app
                try:
                    requests.post(FLASK_WEBHOOK_URL, json=response_data, timeout=5)
                except Exception as webhook_error:
                    logger.error(f"Failed to send webhook: {str(webhook_error)}")
                return response_data
            
            artist_id = artist_result["ArtistId"]
            actual_artist_name = artist_result["Name"]
            
            # Get albums and track counts
            cursor.execute("""
                SELECT Album.Title, COUNT(Track.TrackId) as TrackCount
                FROM Album
                LEFT JOIN Track ON Album.AlbumId = Track.AlbumId
                WHERE Album.ArtistId = ?
                GROUP BY Album.Title
                ORDER BY Album.Title
            """, (artist_id,))
            album_results = cursor.fetchall()
            
            # Get total tracks
            cursor.execute("""
                SELECT COUNT(Track.TrackId)
                FROM Track
                JOIN Album ON Track.AlbumId = Album.AlbumId
                WHERE Album.ArtistId = ?
            """, (artist_id,))
            total_tracks = cursor.fetchone()[0]
            
            # Get genres
            cursor.execute("""
                SELECT Genre.Name, COUNT(Track.TrackId) as TrackCount
                FROM Genre
                JOIN Track ON Genre.GenreId = Track.GenreId
                JOIN Album ON Track.AlbumId = Album.AlbumId
                WHERE Album.ArtistId = ?
                GROUP BY Genre.Name
                ORDER BY TrackCount DESC
                LIMIT 3
            """, (artist_id,))
            genre_results = cursor.fetchall()
            main_genres = [genre["Name"] for genre in genre_results]
            
            # Format albums data
            albums = []
            for album in album_results:
                albums.append({
                    "title": album["Title"],
                    "track_count": album["TrackCount"]
                })
            
            # Prepare the response data
            response_data = {
                "status": "success",
                "artist_name": artist_name,  # Original search term
                "name": actual_artist_name,  # Actual artist name from DB
                "artist_id": artist_id,
                "albums": albums,
                "total_tracks": total_tracks,
                "main_genres": main_genres
            }
            
            # Send result back to Flask app
            try:
                logger.info(f"Sending webhook with artist data: {actual_artist_name}")
                requests.post(FLASK_WEBHOOK_URL, json=response_data, timeout=5)
            except Exception as webhook_error:
                logger.error(f"Failed to send webhook: {str(webhook_error)}")
            
            return response_data
            
        finally:
            conn.close()
            
    except sqlite3.Error as e:
        logger.error(f"Database error: {str(e)}")
        response_data = {
            "status": "error",
            "message": f"Database error: {str(e)}",
            "artist_name": artist_name
        }
        # Send error back to Flask app
        try:
            requests.post(FLASK_WEBHOOK_URL, json=response_data, timeout=5)
        except Exception as webhook_error:
            logger.error(f"Failed to send webhook: {str(webhook_error)}")
        return response_data
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        response_data = {
            "status": "error",
            "message": f"An unexpected error occurred: {str(e)}",
            "artist_name": artist_name
        }
        # Send error back to Flask app
        try:
            requests.post(FLASK_WEBHOOK_URL, json=response_data, timeout=5)
        except Exception as webhook_error:
            logger.error(f"Failed to send webhook: {str(webhook_error)}")
        return response_data
