from flask import Flask, request, jsonify, render_template
import sqlite3
import re
import os
import json
from flask_cors import CORS
import openai
from dotenv import load_dotenv
from contextlib import contextmanager
import requests
import logging
from typing import Dict, Any, Optional, Generator, List, Tuple, Union
from datetime import datetime
import time
# import sys
# from pathlib import Path

# # Add the project root directory to the Python path
# project_root = Path(__file__).resolve().parent
# sys.path.insert(0, str(project_root))

# Now the import should be found
from inngest_setup.functions.get_artist import inngest_client

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Initialize OpenAI API using key from .env file
openai.api_key = os.getenv("OPENAI_API_KEY")

# Environment variables and configuration
INNGEST_URL = os.getenv("INNGEST_URL", "http://localhost:8288/e")
INNGEST_FUNCTION_NAME = os.getenv("INNGEST_FUNCTION_NAME", "get-artist")
INNGEST_ENABLED = True  # Always require Inngest

# Log configuration
logger.info(f"Using Inngest URL: {INNGEST_URL}")
if not INNGEST_URL:
    logger.error("INNGEST_URL environment variable is not set! Artist search will fail.")

# Store recent results temporarily (for demo purposes - in production use Redis/database)
RECENT_ARTIST_RESULTS: Dict[str, Dict[str, Any]] = {}

# Root route to serve the main page
@app.route('/')
def index():
    """Serve the main chat application page"""
    return render_template('index.html')

# Add this before the error handlers
@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Check if database is accessible
        with get_db_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        
        # Check if OpenAI API key is configured
        api_key_configured = bool(openai.api_key)
        
        return jsonify({
            "status": "ok",
            "version": "1.0.0",
            "database": "connected",
            "openai_api": "configured" if api_key_configured else "not_configured"
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors"""
    return render_template('error.html', error_code=404, error_message="The page you're looking for doesn't exist."), 404

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors"""
    return render_template('error.html', error_code=500, error_message="Something went wrong on our end. Please try again later."), 500

@app.errorhandler(403)
def forbidden(e):
    """Handle 403 errors"""
    return render_template('error.html', error_code=403, error_message="You don't have permission to access this resource."), 403

@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections.
    
    Yields:
        sqlite3.Connection: Database connection
    """
    conn = sqlite3.connect('Chinook.db')
    try:
        yield conn
    finally:
        conn.close()

def call_openai(system_message: str, user_message: str, temperature: float = 0) -> str:
    """Utility function for OpenAI API calls"""
    try:
        # Try with new OpenAI client (v1.0+)
        try:
            from openai import OpenAI
            client = OpenAI()
            # Remove proxies parameter if it's causing issues
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except TypeError as e:
            # Handle the specific TypeError for proxies
            if "got an unexpected keyword argument 'proxies'" in str(e):
                logger.warning("OpenAI client error with proxies, retrying without proxies")
                from openai import OpenAI
                client = OpenAI()
                # Create a new client without the proxies parameter
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=temperature
                )
                return response.choices[0].message.content.strip()
            else:
                raise
    except Exception as e:
        logger.error(f"Error with new OpenAI client: {str(e)}")
        
        try:
            # Try with explicit version for legacy API (v0.x)
            import openai
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                temperature=temperature
            )
            return response['choices'][0]['message']['content'].strip()
        except Exception as legacy_error:
            logger.error(f"Error with legacy OpenAI client: {str(legacy_error)}")
            
            # Last resort fallback - return a default response
            logger.warning("Both OpenAI API calls failed, returning default response")
            return "I'm sorry, I couldn't process that request due to an API issue. Please try again later."

@app.route('/message', methods=['POST'])
def handle_message() -> Dict[str, str]:
    """
    Handle incoming messages from the frontend.
    
    Returns:
        Dict[str, str]: JSON response containing the chatbot's response
    """
    user_message = request.json.get('message', '')
    response = get_chatbot_response(user_message)
    return jsonify({"response": response})

@app.route('/trigger-artist', methods=['POST'])
def trigger_artist():
    """
    Endpoint to trigger an Inngest function to fetch artist information.
    This provides an asynchronous way to look up artist details.
    """
    if not request.is_json:
        logger.error("Trigger artist endpoint received non-JSON payload")
        return jsonify({"status": "error", "message": "Expected JSON payload"}), 400
    
    try:
        data = request.json
        
        # Validate required fields
        if not data.get("artist_name"):
            logger.error("Trigger artist missing artist_name field")
            return jsonify({"status": "error", "message": "Missing artist_name field"}), 400
        
        artist_name = data.get("artist_name")
        logger.info(f"Triggering Inngest function for artist: {artist_name}")
        
        response = check_artist_via_inngest(artist_name)
        
        # Return a success response with the message from check_artist_via_inngest
        return jsonify({
            "status": "success", 
            "message": "Request processed",
            "response": response
        })
    
    except Exception as e:
        logger.exception(f"Error triggering artist function: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/inngest', methods=['POST', 'PUT'])
def inngest_webhook():
    """Endpoint for Inngest to send events (legacy endpoint, retained for compatibility)"""
    # Log the received request
    logger.info(f"Inngest webhook received (legacy endpoint): {request.method}")
    logger.info(f"Request data: {request.data}")
    
    # Inngest dev server sends periodic health checks
    # Just acknowledge these, no processing needed
    return jsonify({"status": "received"})

def extract_limit(message: str) -> Optional[int]:
    """
    Extract a numeric limit from the message.
    
    Args:
        message: The message to extract limit from
        
    Returns:
        Optional[int]: The extracted limit or None if not found
    """
    # Look for various patterns:
    # - "top 10"
    # - "10 most"
    # - "10 top"
    # - "show me 10"
    # - "limit to 10"
    # - just a number at the beginning like "5 artists"
    patterns = [
        r'top\s+(\d+)',              # "top 10"
        r'(\d+)\s+most',             # "10 most"
        r'(\d+)\s+top',              # "10 top"
        r'show\s+me\s+(\d+)',        # "show me 10"
        r'limit\s+(?:to\s+)?(\d+)',  # "limit to 10" or "limit 10"
        r'^(\d+)\s+',                # "5 artists" (number at start)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message.lower())
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                pass
    
    return None

def is_openai_configured() -> bool:
    """
    Check if OpenAI API is properly configured.
    
    Returns:
        bool: True if OpenAI is configured, False otherwise
    """
    if not openai.api_key:
        logger.warning("OpenAI API key is not set")
        return False
    
    # Print the first few characters of the key (for debugging)
    if openai.api_key:
        key_preview = openai.api_key[:5] + "..." + openai.api_key[-3:] if len(openai.api_key) > 10 else "Invalid key format"
        logger.info(f"Using OpenAI API key: {key_preview}")
    
    return bool(openai.api_key)

# Add this helper function to check for artist info using Inngest
async def check_artist_via_inngest(artist_name: str) -> str:
    """Process an artist info request via Inngest"""
    logger.info(f"Checking artist via Inngest: {artist_name}")
    
    try:
        # Store that we're looking for this artist
        search_key = artist_name.lower()
        RECENT_ARTIST_RESULTS[search_key] = {"status": "pending"}
        
        # Trigger the Inngest event properly
        await inngest_client.send(
            name="get.artist",  # This must match the trigger event name in get_artist.py
            data={"artist_name": artist_name}
        )
        
        return f"I'm looking up information about {artist_name}. Please check back in a moment or ask me again soon for the results."
        
    except Exception as e:
        logger.error(f"Error triggering Inngest event: {str(e)}")
        RECENT_ARTIST_RESULTS[search_key] = {
            "status": "error",
            "message": f"Error triggering search: {str(e)}"
        }
        return f"I'm having trouble looking up information about {artist_name}. Please try again later."

# Update the get_chatbot_response function to use Inngest for artist queries
def get_chatbot_response(user_message: str) -> str:
    """
    Process user message and generate response.
    
    Args:
        user_message: The user's message to process
        
    Returns:
        str: The chatbot's response
    """
    logger.info(f"Received message: {user_message}")
    
    # Check OpenAI configuration
    openai_available = is_openai_configured()
    if not openai_available:
        logger.warning("OpenAI not configured properly")
    
    # Check if the message is simple enough to handle without AI
    if user_message.lower() in ["hi", "hello", "hey"]:
        return "I'm here to help! You can ask for reports like 'Show me top 10 artists', 'Report on albums by Queen', or 'Which genres have the most tracks?'"
    
    # Check for specific track+artist query (e.g., "more about mofo by u2")
    track_artist_match = re.search(r'(?:more|about|info|tell|song)\s+(?:about|on|me|for)?\s+([a-z0-9 &\']+)\s+by\s+([a-z0-9 &\']+)', user_message.lower())
    if track_artist_match:
        track_name = track_artist_match.group(1).strip()
        artist_name = track_artist_match.group(2).strip()
        logger.info(f"Detected specific track+artist query: {track_name} by {artist_name}")
        return get_track_by_artist(track_name, artist_name)
    
    # Handle "who is X" queries using Inngest for artist information
    if re.match(r'^\s*who\s+is\s+([a-z0-9 &\']+)\s*$', user_message.lower()):
        artist_name = re.match(r'^\s*who\s+is\s+([a-z0-9 &\']+)\s*$', user_message.lower()).group(1).strip()
        return check_artist_via_inngest(artist_name)
        
    # Quick check for Mofo queries
    if "mofo" in user_message.lower() and "u2" in user_message.lower():
        return get_track_by_artist("Mofo", "U2")
    
    # Use rule-based approach as fallback    
    rule_intent, rule_entities = classify_intent(user_message)
    limit = extract_limit(user_message) or 5
    rule_entities["limit"] = limit
    
    try:
        # Try using OpenAI for all queries if available
        if openai_available:
            logger.info("Using OpenAI to understand the query")
            # Use OpenAI to understand the intent
            query_result = analyze_query_with_openai(user_message)
            logger.info(f"OpenAI classified query as: {query_result}")
            
            query_type = query_result.get("query_type", "unknown")
            
            if query_type == "song_info" and "song_name" in query_result:
                song_name = query_result["song_name"]
                return get_song_info(song_name)
            
            if query_type == "artist_info" and "artist_name" in query_result:
                artist_name = query_result["artist_name"]
                return check_artist_via_inngest(artist_name)
                
            if query_type == "album_tracks" and "album_name" in query_result:
                album_name = query_result["album_name"]
                return get_album_tracks(album_name)
                
            if query_type == "top_artists":
                limit = query_result.get("limit", 5)
                return generate_artist_tracks_report(limit)
                
            if query_type == "top_genres":
                limit = query_result.get("limit", 5)
                return generate_genre_report(limit)
        
        # If OpenAI didn't work or isn't available, fall back to rule-based pattern matching
        
        # Check for song related queries - make the regex more flexible
        if "artist" in user_message.lower() and re.search(r'(?:artist|who).+(?:for|of|sang|sings|performs|by)\s+([a-z0-9 &\']+)', user_message.lower()):
            match = re.search(r'(?:artist|who).+(?:for|of|sang|sings|performs|by)\s+([a-z0-9 &\']+)', user_message.lower())
            song_name = match.group(1).strip()
            logger.info(f"Detected song query for: {song_name}")
            return get_song_info(song_name)
        
        # Traditional pattern matching (from previous version)        
        if re.search(r'who\s+(?:is|made|sang|performs|created|wrote)\s+(?:the\s+)?(?:song|track)?\s*([a-z0-9 &\']+)', user_message.lower()):
            song_name = re.search(r'who\s+(?:is|made|sang|performs|created|wrote)\s+(?:the\s+)?(?:song|track)?\s*([a-z0-9 &\']+)', user_message.lower()).group(1).strip()
            return get_song_info(song_name)
        
        # Check for "who is the artist for" queries with a more general pattern
        if re.search(r'who\s+is\s+(?:the\s+)?artist\s+(?:for|of)\s+([a-z0-9 &\']+)', user_message.lower()):
            song_name = re.search(r'who\s+is\s+(?:the\s+)?artist\s+(?:for|of)\s+([a-z0-9 &\']+)', user_message.lower()).group(1).strip()
            return get_song_info(song_name)
        
        # Try to process using the knowledge base for artist info
        if rule_entities.get("artist_name"):
            artist_name = rule_entities["artist_name"]
            return check_artist_via_inngest(artist_name)
        
        # If we have a report request that might involve artist information
        if rule_intent == "report" and rule_entities["report_type"] in ["artist_specific", "artist_tracks", "artist_albums"]:
            potential_artist_match = re.search(r'about\s+([a-z0-9 &\']+)', user_message.lower())
            if potential_artist_match:
                artist_name = potential_artist_match.group(1).strip()
                if len(artist_name) > 2:  # Avoid matching on very short words
                    return check_artist_via_inngest(artist_name)
        
        # Check for album track listing queries
        if re.search(r'(?:tell|show|what|list)\s+(?:me\s+)?(?:the\s+)?(?:songs|tracks)\s+(?:in|on|from)\s+(?:the\s+)?(?:album\s+)?([a-z0-9 &\']+)', user_message.lower()):
            album_name = re.search(r'(?:tell|show|what|list)\s+(?:me\s+)?(?:the\s+)?(?:songs|tracks)\s+(?:in|on|from)\s+(?:the\s+)?(?:album\s+)?([a-z0-9 &\']+)', user_message.lower()).group(1).strip()
            return get_album_tracks(album_name)
        
        # For more complex queries, try dynamic SQL generation via OpenAI
        if openai_available:
            try:
                logger.info("Attempting dynamic SQL query via OpenAI")
                result = execute_dynamic_query(user_message)
                logger.info("Dynamic query successful")
                return result
            except Exception as sql_error:
                logger.error(f"Dynamic SQL error: {str(sql_error)}")
                # If dynamic query fails, fall back to rule-based approach
                return generate_report(rule_intent, rule_entities)
        
        # Use rule-based approach for standard reports
        return generate_report(rule_intent, rule_entities)
            
    except Exception as e:
        logger.error(f"Error in get_chatbot_response: {str(e)}")
        # Last resort fallback
        return generate_report(rule_intent, rule_entities)

def analyze_query_with_openai(user_message: str) -> Dict[str, Any]:
    """
    Use OpenAI to analyze the user's query and determine what they're asking about.
    
    Args:
        user_message: The user's query message
        
    Returns:
        Dict[str, Any]: Analysis result containing query type and relevant entities
    """
    system_message = """
    You are a music database assistant. Analyze the user's query and determine what type of information they're asking for.
    
    Important rules:
    1. "Who is X" queries are almost always asking about an artist, not a song.
    2. Only classify as song_info if they're clearly asking about a specific song.
    3. If there's ambiguity, prefer artist_info over song_info.
    
    Return a JSON object with the following structure:
    {
        "query_type": "song_info" | "artist_info" | "album_tracks" | "top_artists" | "top_genres" | "unknown",
        "song_name": "name of song if applicable",
        "artist_name": "name of artist if applicable",
        "album_name": "name of album if applicable",
        "limit": number of results to return (default: 5)
    }
    """
    
    try:
        result = call_openai(system_message, user_message)
        logger.info(f"OpenAI analysis result: {result}")
        
        # Extract JSON from the response
        json_match = re.search(r'({.*})', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        else:
            logger.warning("Could not find JSON in OpenAI response")
            return {"query_type": "unknown"}
    
    except Exception as e:
        logger.error(f"Error analyzing query with OpenAI: {str(e)}")
        return {"query_type": "unknown"}

def get_specific_song_info(song_name):
    """Get information about a specific song by exact name"""
    try:
        connection = sqlite3.connect('Chinook.db')
        cursor = connection.cursor()
        
        # Find song by exact name (case-insensitive)
        cursor.execute("""
            SELECT Track.Name, Artist.Name, Album.Title, Genre.Name, Track.Composer, Track.Milliseconds 
            FROM Track 
            JOIN Album ON Track.AlbumId = Album.AlbumId 
            JOIN Artist ON Album.ArtistId = Artist.ArtistId 
            JOIN Genre ON Track.GenreId = Genre.GenreId 
            WHERE LOWER(Track.Name) = LOWER(?)
        """, (song_name,))
        
        track = cursor.fetchone()
        connection.close()
        
        if not track:
            # Try a more flexible search
            return get_song_info(song_name)
        
        # Format the response
        track_name, artist, album, genre, composer, duration_ms = track
        
        # Convert milliseconds to minutes:seconds
        minutes = int(duration_ms / 60000)
        seconds = int((duration_ms % 60000) / 1000)
        
        response = f"**{track_name}**\n\n"
        response += f"Artist: {artist}\n"
        response += f"Album: {album}\n"
        response += f"Genre: {genre}\n"
        
        if composer and composer.strip():
            response += f"Composer: {composer}\n"
            
        response += f"Duration: {minutes}:{seconds:02d}\n"
        
        return response
        
    except Exception as e:
        print(f"Error getting specific song info: {str(e)}")
        return f"I encountered an error while looking up information about the song '{song_name}'."

def classify_with_openai(message: str) -> Tuple[str, Dict[str, Any]]:
    """
    Use OpenAI to classify the user's intent and extract entities.
    
    Args:
        message: The user's message to classify
        
    Returns:
        Tuple[str, Dict[str, Any]]: Intent and entities extracted from the message
    """
    system_message = """
    You are an intelligent music database assistant. 
    Your task is to analyze user queries about music and extract structured information.
    
    For each query, identify:
    1. The primary intent (report, greeting, help, or unknown)
    2. For report intents, identify these entities:
       - report_type: One of [artist_tracks, artist_albums, genre, album, artist_specific, artist_list]
       - limit: How many results to return (default: 5)
       - artist_name: Name of a specific artist (if mentioned)
       
    Return your analysis as valid JSON with this structure:
    {
        "intent": "report|greeting|help|unknown",
        "entities": {
            "report_type": "artist_tracks|artist_albums|genre|album|artist_specific|artist_list",
            "limit": 5,
            "artist_name": null
        }
    }
    """
    
    try:
        ai_response = call_openai(system_message, message, temperature=0.1)
        
        # Handle potential issues with the response
        if not ai_response.startswith("{"):
            # Look for a JSON object within the response
            match = re.search(r'({.*})', ai_response, re.DOTALL)
            if match:
                ai_response = match.group(1)
            else:
                raise ValueError("OpenAI response doesn't contain valid JSON")
                
        result = json.loads(ai_response)
        
        # Validate required fields
        intent = result.get("intent", "unknown")
        entities = result.get("entities", {})
        
        # Set defaults if missing
        if "report_type" not in entities:
            entities["report_type"] = "artist_tracks"
        if "limit" not in entities:
            entities["limit"] = 5
        if "artist_name" not in entities:
            entities["artist_name"] = None
            
        return intent, entities
        
    except Exception as e:
        logger.error(f"Error parsing OpenAI response: {str(e)}")
        # Return default values
        return "unknown", {"report_type": "artist_tracks", "limit": 5, "artist_name": None}

def classify_intent(message):
    """Classify the user's intent and extract entities using rule-based approach"""
    # Initialize entities with default values
    entities = {
        "limit": 5,
        "report_type": "artist_tracks",
        "artist_name": None
    }
    
    message = message.lower()
    
    # Determine limit (how many results to return)
    if any(phrase in message for phrase in ["only one", "just one", "single", "top 1"]):
        entities["limit"] = 1
    else:
        number_match = re.search(r'top (\d+)', message)
        if number_match:
            entities["limit"] = int(number_match.group(1))
    
    # Extract artist name if present - be more flexible with pattern
    artist_match = re.search(r'by\s+([a-z0-9 &\']+)', message)
    if not artist_match:
        # Try alternative pattern without 'by'
        artist_match = re.search(r'albums?\s+(?:from|of)\s+([a-z0-9 &\']+)', message)
        
    if artist_match:
        entities["artist_name"] = artist_match.group(1).strip()
    
    # Check if asking for all artists
    if "all artists" in message or "list artists" in message or "all the artists" in message:
        entities["report_type"] = "artist_list"
        entities["limit"] = 275  # Maximum number of artists
    
    # Determine report type based on keywords in message
    elif entities["artist_name"]:
        entities["report_type"] = "artist_specific"
    elif any(word in message for word in ["genre", "genres", "category", "categories", "type", "types"]):
        entities["report_type"] = "genre"
    elif any(word in message for word in ["album", "albums", "record", "records"]):
        entities["report_type"] = "album"
    elif any(word in message for word in ["artist", "artists", "band", "bands", "musician", "musicians"]):
        if "album" in message:
            entities["report_type"] = "artist_albums"
        else:
            entities["report_type"] = "artist_tracks"
    elif any(word in message for word in ["track", "tracks", "song", "songs"]):
        entities["report_type"] = "artist_tracks"
    
    # Detect if this is a report request - be more flexible with spelling
    report_keywords = ["report", "repport", "show", "tell", "which", "what", "list", "give", "most", "top"]
    is_report_request = any(keyword in message for keyword in report_keywords)
    
    # Determine intent
    if "hi" in message or "hello" in message or "hey" in message:
        intent = "greeting"
    elif "help" in message:
        intent = "help"
    elif is_report_request:
        intent = "report"
    else:
        intent = "unknown"
    
    return intent, entities

def generate_report(intent, entities):
    """Generate appropriate report based on intent and entities"""
    report_type = entities["report_type"]
    limit = entities["limit"]
    artist_name = entities["artist_name"]
    
    # For standard reports, use pre-defined functions
    if report_type == "artist_specific" and artist_name:
        return generate_artist_specific_report(artist_name)
    elif report_type == "artist_list":
        return generate_artist_list_report(limit)
    elif report_type == "artist_tracks":
        return generate_artist_tracks_report(limit)
    elif report_type == "artist_albums":
        return generate_artist_albums_report(limit)
    elif report_type == "genre":
        return generate_genre_report(limit)
    elif report_type == "album":
        return generate_album_report(limit)
    else:
        return generate_artist_tracks_report(limit)

def generate_artist_list_report(limit=50):
    """Generate a list of artists in the database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT Artist.Name
                FROM Artist
                ORDER BY Artist.Name
                LIMIT {limit}
            """)
            rows = cursor.fetchall()
            
            # Get total count of artists
            cursor.execute("SELECT COUNT(*) FROM Artist")
            total_count = cursor.fetchone()[0]

        report = f"Artists in the database (showing {min(limit, len(rows))} of {total_count}):\n"
        for row in rows:
            report += f"• {row[0]}\n"
        
        if len(rows) < total_count:
            report += f"\n(Add 'show all' to your request to see all {total_count} artists)"
        
        return report
    except Exception as e:
        logger.error(f"Error generating artist list report: {str(e)}")
        return "Sorry, I couldn't retrieve the list of artists right now."

def generate_artist_tracks_report(limit=5):
    """Generate a report of artists with the most tracks"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT Artist.Name, COUNT(Track.TrackId) 
                FROM Track 
                JOIN Album ON Track.AlbumId = Album.AlbumId 
                JOIN Artist ON Album.ArtistId = Artist.ArtistId 
                GROUP BY Artist.Name 
                ORDER BY COUNT(Track.TrackId) DESC 
                LIMIT {limit}
            """)
            rows = cursor.fetchall()

        report = f"Top {limit} Artists with Most Tracks:\n"
        for row in rows:
            report += f"{row[0]}: {row[1]} tracks\n"
        return report
    except Exception as e:
        logger.error(f"Error generating artist tracks report: {str(e)}")
        return "Sorry, I couldn't retrieve the artist tracks report right now."

def generate_artist_albums_report(limit=5):
    connection = sqlite3.connect('Chinook.db')
    cursor = connection.cursor()
    cursor.execute(f"""
        SELECT Artist.Name, COUNT(Album.AlbumId) 
        FROM Album 
        JOIN Artist ON Album.ArtistId = Artist.ArtistId 
        GROUP BY Artist.Name 
        ORDER BY COUNT(Album.AlbumId) DESC 
        LIMIT {limit}
    """)
    rows = cursor.fetchall()
    connection.close()

    report = f"Top {limit} Artists with Most Albums:\n"
    for row in rows:
        report += f"{row[0]}: {row[1]} albums\n"
    return report

def generate_genre_report(limit=5):
    connection = sqlite3.connect('Chinook.db')
    cursor = connection.cursor()
    cursor.execute(f"""
        SELECT Genre.Name, COUNT(Track.TrackId) 
        FROM Track 
        JOIN Genre ON Track.GenreId = Genre.GenreId 
        GROUP BY Genre.Name 
        ORDER BY COUNT(Track.TrackId) DESC 
        LIMIT {limit}
    """)
    rows = cursor.fetchall()
    connection.close()

    report = f"Top {limit} Genres with Most Tracks:\n"
    for row in rows:
        report += f"{row[0]}: {row[1]} tracks\n"
    return report

def generate_album_report(limit=5):
    connection = sqlite3.connect('Chinook.db')
    cursor = connection.cursor()
    cursor.execute(f"""
        SELECT Album.Title, Artist.Name, COUNT(Track.TrackId) 
        FROM Track 
        JOIN Album ON Track.AlbumId = Album.AlbumId 
        JOIN Artist ON Album.ArtistId = Artist.ArtistId 
        GROUP BY Album.Title 
        ORDER BY COUNT(Track.TrackId) DESC 
        LIMIT {limit}
    """)
    rows = cursor.fetchall()
    connection.close()

    report = f"Top {limit} Albums with Most Tracks:\n"
    for row in rows:
        report += f"{row[0]} by {row[1]}: {row[2]} tracks\n"
    return report

def generate_artist_specific_report(artist_name):
    connection = sqlite3.connect('Chinook.db')
    cursor = connection.cursor()
    
    # First check if artist exists - use case-insensitive LIKE with %
    cursor.execute("SELECT ArtistId, Name FROM Artist WHERE LOWER(Name) LIKE ?", (f"%{artist_name.lower()}%",))
    results = cursor.fetchall()
    
    if not results:
        # Suggest similar artists if no match found
        connection.close()
        return find_similar_artists(artist_name)
    
    # If we have multiple matches, use the closest one
    artist_id = None
    exact_name = None
    
    # Check for exact match first
    for id, name in results:
        if name.lower() == artist_name.lower():
            artist_id = id
            exact_name = name
            break
    
    # If no exact match, take the first partial match
    if artist_id is None and results:
        artist_id = results[0][0]
        exact_name = results[0][1]
    
    # Get album and track counts
    cursor.execute("""
        SELECT Artist.Name, COUNT(DISTINCT Album.AlbumId) as AlbumCount, COUNT(Track.TrackId) as TrackCount 
        FROM Artist 
        JOIN Album ON Artist.ArtistId = Album.ArtistId 
        JOIN Track ON Album.AlbumId = Track.AlbumId 
        WHERE Artist.ArtistId = ?
        GROUP BY Artist.Name
    """, (artist_id,))
    
    overview = cursor.fetchone()
    
    # If no albums/tracks, just use the artist info
    if not overview:
        cursor.execute("SELECT Name FROM Artist WHERE ArtistId = ?", (artist_id,))
        artist_name_result = cursor.fetchone()
        if artist_name_result:
            report = f"Artist Report: {artist_name_result[0]}\n"
            report += "This artist has no albums or tracks in the database."
            connection.close()
            return report
    
    # Get their albums
    cursor.execute("""
        SELECT Album.Title, COUNT(Track.TrackId) 
        FROM Album 
        JOIN Track ON Album.AlbumId = Track.AlbumId 
        WHERE Album.ArtistId = ? 
        GROUP BY Album.Title
        ORDER BY Album.Title
    """, (artist_id,))
    
    albums = cursor.fetchall()
    connection.close()
    
    # Format the report
    report = f"Artist Report: {overview[0]}\n"
    report += f"Total Albums: {overview[1]}\n"
    report += f"Total Tracks: {overview[2]}\n\n"
    
    if albums:
        report += "Albums:\n"
        for album in albums:
            report += f"• {album[0]}: {album[1]} tracks\n"
    
    return report

def find_similar_artists(search_term):
    """Find artists with names similar to the search term"""
    connection = sqlite3.connect('Chinook.db')
    cursor = connection.cursor()
    
    # Get list of all artists for suggesting similar ones
    cursor.execute("SELECT Name FROM Artist ORDER BY Name")
    all_artists = [row[0] for row in cursor.fetchall()]
    connection.close()
    
    # Simple string distance matching - find artists that contain any word from the search
    search_words = search_term.lower().split()
    similar_artists = []
    
    for artist in all_artists:
        artist_lower = artist.lower()
        for word in search_words:
            if len(word) > 2 and word in artist_lower:  # Only match on words with 3+ characters
                similar_artists.append(artist)
                break
    
    if similar_artists:
        response = f"Sorry, I couldn't find an artist matching '{search_term}'\n\n"
        response += "Did you mean one of these?\n"
        # Show up to 10 similar artists
        for artist in similar_artists[:10]:
            response += f"• {artist}\n"
        return response
    else:
        return f"Sorry, I couldn't find an artist matching '{search_term}'. Try another artist name or check the spelling."

def generate_sql_from_prompt(user_prompt: str) -> Optional[str]:
    """Generate a SQL query for the Chinook database using OpenAI"""
    logger.info(f"Generating SQL for prompt: {user_prompt}")
    
    system_message = """
    You are a helpful SQL assistant. Generate a SQL query for a SQLite Chinook database.
    
    The Chinook database has these tables:
    - Album (AlbumId, Title, ArtistId)
    - Artist (ArtistId, Name)
    - Customer (CustomerId, FirstName, LastName, Company, Address, City, State, Country, PostalCode, Phone, Fax, Email, SupportRepId)
    - Employee (EmployeeId, LastName, FirstName, Title, ReportsTo, BirthDate, HireDate, Address, City, State, Country, PostalCode, Phone, Fax, Email)
    - Genre (GenreId, Name)
    - Invoice (InvoiceId, CustomerId, InvoiceDate, BillingAddress, BillingCity, BillingState, BillingCountry, BillingPostalCode, Total)
    - InvoiceLine (InvoiceLineId, InvoiceId, TrackId, UnitPrice, Quantity)
    - MediaType (MediaTypeId, Name)
    - Playlist (PlaylistId, Name)
    - PlaylistTrack (PlaylistId, TrackId)
    - Track (TrackId, Name, AlbumId, MediaTypeId, GenreId, Composer, Milliseconds, Bytes, UnitPrice)
    
    Return ONLY the SQL query without any explanation or markdown formatting.
    Make sure the query is valid SQLite syntax.
    Limit results to 20 rows unless specified otherwise.
    """
    
    try:
        # Try generating SQL with OpenAI
        sql_query = call_openai(system_message, user_prompt)
        logger.info(f"Generated SQL query successfully")
        
        # Remove markdown code blocks if present
        sql_query = re.sub(r'```sql\s*|\s*```', '', sql_query)
        
        return sql_query
        
    except Exception as e:
        logger.error(f"SQL generation failed: {str(e)}")
        
        # Return appropriate hardcoded query based on keywords in the prompt
        logger.info("Falling back to hardcoded queries")
        
        # Common queries as fallbacks
        if "artist" in user_prompt.lower() and any(word in user_prompt.lower() for word in ["popular", "top", "most"]):
            return """
            SELECT Artist.Name, COUNT(Track.TrackId) as TrackCount 
            FROM Artist 
            JOIN Album ON Artist.ArtistId = Album.ArtistId 
            JOIN Track ON Album.AlbumId = Track.AlbumId 
            GROUP BY Artist.Name 
            ORDER BY TrackCount DESC 
            LIMIT 10
            """
        elif "genre" in user_prompt.lower():
            return """
            SELECT Genre.Name, COUNT(Track.TrackId) as TrackCount 
            FROM Genre 
            JOIN Track ON Genre.GenreId = Track.GenreId 
            GROUP BY Genre.Name 
            ORDER BY TrackCount DESC 
            LIMIT 10
            """
        elif "album" in user_prompt.lower():
            return """
            SELECT Album.Title, Artist.Name, COUNT(Track.TrackId) as TrackCount
            FROM Album
            JOIN Artist ON Album.ArtistId = Artist.ArtistId
            JOIN Track ON Album.AlbumId = Track.AlbumId
            GROUP BY Album.Title
            ORDER BY TrackCount DESC
            LIMIT 10
            """
        else:
            logger.warning("No matching hardcoded query for prompt")
            return None

def execute_dynamic_query(user_query):
    """Generate and execute a dynamic SQL query based on natural language"""
    try:
        # Generate SQL from the natural language query
        sql_query = generate_sql_from_prompt(user_query)
        
        if not sql_query:
            return "I had trouble generating a SQL query for that request."
        
        print(f"Generated SQL: {sql_query}")
        
        # Execute the query
        connection = sqlite3.connect('Chinook.db')
        cursor = connection.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        
        # Get column names
        column_names = [description[0] for description in cursor.description]
        connection.close()
        
        # Format the results
        if not rows:
            return "No data found for that query."
        
        # Create a formatted report without the header styling
        if len(column_names) == 1:
            # If there's only one column, format as a simple list
            report = ""
            for row in rows:
                report += f"• {row[0]}\n"
        else:
            # For multiple columns, create a more structured format
            report = ""
            for row in rows:
                item_parts = []
                for i, value in enumerate(row):
                    item_parts.append(f"{column_names[i]}: {value}")
                report += f"• {', '.join(item_parts)}\n"
        
        return report
    
    except Exception as e:
        print(f"Error executing dynamic query: {str(e)}")
        return f"I encountered an error: {str(e)}"

def get_artist_info(artist_name: str) -> str:
    """
    Get detailed information about an artist.
    
    Args:
        artist_name: Name of the artist to look up
        
    Returns:
        str: Formatted response with artist details
    """
    try:
        with get_db_connection() as connection:
            cursor = connection.cursor()
            
            # Find artist by name (case-insensitive)
            cursor.execute("SELECT ArtistId, Name FROM Artist WHERE LOWER(Name) LIKE ?", (f"%{artist_name.lower()}%",))
            artist_results = cursor.fetchall()
            
            if not artist_results:
                return f"I couldn't find any information about an artist named '{artist_name}'."
                
            # Use the first match
            artist_id, artist_name = artist_results[0]
            
            # Get album information
            cursor.execute("""
                SELECT Album.Title, COUNT(Track.TrackId) as TrackCount 
                FROM Album 
                LEFT JOIN Track ON Album.AlbumId = Track.AlbumId 
                WHERE Album.ArtistId = ? 
                GROUP BY Album.Title
                ORDER BY Album.Title
            """, (artist_id,))
            albums = cursor.fetchall()
            
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
            """, (artist_id,))
            genres = cursor.fetchall()
            
            # Format the response
            response = f"**{artist_name}**\n\n"
            
            if albums:
                response += f"Albums: {len(albums)}\n"
                response += f"Total Tracks: {total_tracks}\n\n"
                
                if genres:
                    genre_list = ", ".join([genre[0] for genre in genres[:3]])
                    response += f"Main Genres: {genre_list}\n\n"
                
                response += "Albums:\n"
                for album, track_count in albums:
                    response += f"• {album} ({track_count} tracks)\n"
            else:
                response += "No albums or tracks found for this artist in our database."
            
            return response
            
    except Exception as e:
        logger.error(f"Error getting artist info: {str(e)}")
        return f"I encountered an error while looking up information about {artist_name}."

def get_song_info(song_name):
    """Get information about a specific song"""
    try:
        connection = sqlite3.connect('Chinook.db')
        cursor = connection.cursor()
        
        # Find song by name (case-insensitive)
        cursor.execute("""
            SELECT Track.Name, Artist.Name, Album.Title, Genre.Name, Track.Composer, Track.Milliseconds, Track.Bytes, Track.UnitPrice 
            FROM Track 
            JOIN Album ON Track.AlbumId = Album.AlbumId 
            JOIN Artist ON Album.ArtistId = Artist.ArtistId 
            JOIN Genre ON Track.GenreId = Genre.GenreId 
            WHERE LOWER(Track.Name) LIKE ?
        """, (f"%{song_name.lower()}%",))
        
        tracks = cursor.fetchall()
        connection.close()
        
        if not tracks:
            return f"I couldn't find any song matching '{song_name}' in our database."
        
        # Format the response
        if len(tracks) == 1:
            # Single match
            track = tracks[0]
            track_name, artist, album, genre, composer, duration_ms, bytes_size, price = track
            
            # Convert milliseconds to minutes:seconds
            minutes = int(duration_ms / 60000)
            seconds = int((duration_ms % 60000) / 1000)
            
            response = f"**{track_name}**\n\n"
            response += f"Artist: {artist}\n"
            response += f"Album: {album}\n"
            response += f"Genre: {genre}\n"
            
            if composer and composer.strip():
                response += f"Composer: {composer}\n"
                
            response += f"Duration: {minutes}:{seconds:02d}\n"
            
            return response
        else:
            # Multiple matches
            response = f"I found multiple tracks matching '{song_name}':\n\n"
            
            for track in tracks[:5]:  # Limit to 5 results to avoid too long responses
                track_name, artist, album, genre, _, _, _, _ = track
                response += f"• {track_name} by {artist} (Album: {album})\n"
                
            if len(tracks) > 5:
                response += f"\nAnd {len(tracks) - 5} more matches."
                
            return response
        
    except Exception as e:
        print(f"Error getting song info: {str(e)}")
        return f"I encountered an error while looking up information about the song '{song_name}'."

def get_album_tracks(album_name):
    """Get tracks for a specific album"""
    try:
        connection = sqlite3.connect('Chinook.db')
        cursor = connection.cursor()
        
        # Find album by name (case-insensitive)
        cursor.execute("""
            SELECT Album.AlbumId, Album.Title, Artist.Name
            FROM Album 
            JOIN Artist ON Album.ArtistId = Artist.ArtistId 
            WHERE LOWER(Album.Title) LIKE ?
        """, (f"%{album_name.lower()}%",))
        
        albums = cursor.fetchall()
        
        if not albums:
            connection.close()
            return f"I couldn't find any album matching '{album_name}' in our database."
        
        # Use the first matching album
        album_id, album_title, artist_name = albums[0]
        
        # Get tracks for the album
        cursor.execute("""
            SELECT Track.Name, Track.Milliseconds
            FROM Track 
            WHERE Track.AlbumId = ?
            ORDER BY Track.TrackNumber
        """, (album_id,))
        
        tracks = cursor.fetchall()
        connection.close()
        
        # Format the response
        response = f"**{album_title}** by {artist_name}\n\n"
        
        if tracks:
            for i, (track_name, duration_ms) in enumerate(tracks, 1):
                # Convert milliseconds to minutes:seconds
                minutes = int(duration_ms / 60000)
                seconds = int((duration_ms % 60000) / 1000)
                
                response += f"• {track_name} ({minutes}:{seconds:02d})\n"
        else:
            response += "No tracks found for this album."
            
        return response
        
    except Exception as e:
        print(f"Error getting album tracks: {str(e)}")
        return f"I encountered an error while looking up tracks for the album '{album_name}'."

def get_track_by_artist(track_name, artist_name):
    """Get detailed information about a specific track by a specific artist"""
    try:
        connection = sqlite3.connect('Chinook.db')
        cursor = connection.cursor()
        
        # Find the specific track by artist
        cursor.execute("""
            SELECT Track.Name, Artist.Name, Album.Title, Genre.Name, Track.Composer, 
                   Track.Milliseconds, Track.Bytes, Track.UnitPrice 
            FROM Track 
            JOIN Album ON Track.AlbumId = Album.AlbumId 
            JOIN Artist ON Album.ArtistId = Artist.ArtistId 
            JOIN Genre ON Track.GenreId = Genre.GenreId 
            WHERE LOWER(Track.Name) LIKE ? AND LOWER(Artist.Name) LIKE ?
        """, (f"%{track_name.lower()}%", f"%{artist_name.lower()}%"))
        
        tracks = cursor.fetchall()
        connection.close()
        
        if not tracks:
            return f"I couldn't find a track called '{track_name}' by '{artist_name}'."
        
        # Use the first match (most likely the right one given both constraints)
        track = tracks[0]
        track_name, artist, album, genre, composer, duration_ms, bytes_size, price = track
        
        # Convert milliseconds to minutes:seconds
        minutes = int(duration_ms / 60000)
        seconds = int((duration_ms % 60000) / 1000)
        
        # Format detailed response
        response = f"**{track_name}** by {artist}\n\n"
        response += f"Album: {album}\n"
        response += f"Genre: {genre}\n"
        
        if composer and composer.strip():
            response += f"Composer: {composer}\n"
            
        response += f"Duration: {minutes}:{seconds:02d}\n"
        
        # Add some extra details about the track
        response += f"Price: ${price}\n"
        
        # Additional request to get album tracks position
        connection = sqlite3.connect('Chinook.db')
        cursor = connection.cursor()
        cursor.execute("""
            SELECT t.Name, t.TrackNumber 
            FROM Track t
            JOIN Album a ON t.AlbumId = a.AlbumId
            WHERE a.Title = ? 
            ORDER BY t.TrackNumber
        """, (album,))
        album_tracks = cursor.fetchall()
        connection.close()
        
        # Find track position in album
        track_number = None
        for i, (name, number) in enumerate(album_tracks, 1):
            if name.lower() == track_name.lower():
                track_number = i
                break
                
        if track_number:
            response += f"Track #{track_number} on the album\n"
            
        return response
        
    except Exception as e:
        print(f"Error getting track by artist: {str(e)}")
        return f"I encountered an error while looking up information about '{track_name}' by '{artist_name}'."

# Add this webhook route to handle Inngest callbacks
@app.route('/webhook/artist-result', methods=['POST'])
def artist_webhook():
    """
    Webhook endpoint to receive results from the Inngest artist lookup function.
    Stores the results in the RECENT_ARTIST_RESULTS dictionary for retrieval
    in subsequent user queries.
    """
    if not request.is_json:
        logger.error("Webhook received non-JSON payload")
        return jsonify({"status": "error", "message": "Expected JSON payload"}), 400
    
    try:
        data = request.json
        
        # Validate the required fields
        if not data.get("artist_name"):
            logger.error("Webhook missing artist_name field")
            return jsonify({"status": "error", "message": "Missing artist_name field"}), 400
        
        artist_name = data.get("artist_name")
        search_key = artist_name.lower()
        
        # Check for various response types
        if data.get("status") == "not_found":
            RECENT_ARTIST_RESULTS[search_key] = {
                "status": "not_found",
                "name": artist_name
            }
            logger.info(f"Stored not_found result for artist: {artist_name}")
        elif data.get("status") == "error":
            RECENT_ARTIST_RESULTS[search_key] = {
                "status": "error",
                "name": artist_name,
                "message": data.get("message", "An unknown error occurred")
            }
            logger.error(f"Stored error result for artist: {artist_name} - {data.get('message')}")
        else:
            # Store the successful result
            RECENT_ARTIST_RESULTS[search_key] = {
                "status": "success",
                "name": data.get("name", artist_name),
                "albums": data.get("albums", []),
                "total_tracks": data.get("total_tracks", 0),
                "main_genres": data.get("main_genres", [])
            }
            logger.info(f"Stored successful result for artist: {artist_name}")
        
        return jsonify({"status": "success", "message": "Artist information stored"}), 200
    
    except Exception as e:
        logger.exception(f"Error processing artist webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/get-artist-results', methods=['GET'])
def get_artist_results():
    """
    Get the results of a previously triggered artist search.
    This endpoint allows the frontend to poll for results that have been
    asynchronously processed by Inngest.
    """
    artist_name = request.args.get('artist_name', '').lower()
    
    if not artist_name:
        logger.warning("Artist name parameter is missing")
        return jsonify({
            "status": "error",
            "message": "Artist name parameter is required"
        }), 400
    
    logger.info(f"Checking results for artist: '{artist_name}'")
    
    # Make sure we're using lowercase for comparison
    results = RECENT_ARTIST_RESULTS.get(artist_name.lower())
    
    if not results:
        logger.warning(f"No results found for artist: '{artist_name}'")
        return jsonify({
            "status": "not_found",
            "message": f"No results found for artist: '{artist_name}'. Try triggering a search first."
        })
    
    logger.info(f"Returning results for '{artist_name}': {results['status']}")
    
    # Add timestamp if not present
    if "timestamp" not in results:
        results["timestamp"] = datetime.now().isoformat()
        
    return jsonify(results)

if __name__ == '__main__':
    # Use environment variables with sensible defaults for production
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
