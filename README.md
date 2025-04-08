# Music Chatbot

A Flask-based chatbot application that allows users to query a music database and get information about artists, albums, and songs.

## Features

- Conversational interface for querying music information
- Artist search functionality with asynchronous processing
- Database integration with SQLite (Chinook database)
- OpenAI integration for natural language processing

## Tech Stack

- Backend: Flask
- Frontend: HTML, CSS, JavaScript
- Database: SQLite (Chinook)
- Async Processing: Inngest
- AI: OpenAI GPT-3.5

## Setup and Installation

### Prerequisites

- Python 3.8+
- Chinook.db (SQLite database)
- OpenAI API key

### Installation

1. Clone the repository:
   ```
   git clone <your-repo-url>
   cd chatbot_project
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file in the project root with:
   ```
   OPENAI_API_KEY=your_openai_api_key
   FLASK_ENV=development  # For local development
   ```

5. Ensure you have the Chinook.db file in the project root

### Running Locally

1. Start the Flask application:
   ```
   python app.py
   ```

2. Open a web browser and go to:
   ```
   http://localhost:5000
   ```

## Deployment

The application is configured for deployment on Render:

1. Set up a new Web Service in Render
2. Link to your GitHub repository
3. Set the build command to: `pip install -r requirements.txt`
4. Set the start command to: `gunicorn app:app`
5. Add environment variables:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `FLASK_ENV`: production

## Project Structure

```
chatbot_project/
├── app.py              # Main Flask application
├── Procfile            # For deployment to Render
├── requirements.txt    # Python dependencies
├── Chinook.db          # SQLite database
├── static/             # Static assets
│   ├── style.css       # CSS styles
│   └── script.js       # JavaScript code
├── templates/          # HTML templates
│   └── index.html      # Main chat interface
└── inngest/            # Inngest integration (optional)
    ├── inngest_app.py
    └── functions/
        └── get_artist.py
```

## License

[MIT](LICENSE) 