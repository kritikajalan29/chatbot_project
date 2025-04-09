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

## Deploying with Inngest for Background Processing

This application uses [Inngest](https://www.inngest.com/) to handle background processing for artist information lookups. This separation of concerns:

1. Makes the application more scalable
2. Improves the user experience by not blocking the UI during database queries
3. Allows for retries and better error handling
4. Enables future expansion to more complex background tasks

### Architecture Overview

```
   ┌───────────────┐      HTTP Request     ┌──────────────┐
   │   Flask App   │────────────────────→ │  Inngest.io  │
   │   (Web UI)    │                       │  Event Queue │
   └───────┬───────┘                       └───────┬──────┘
           │                                       │
           │                                       │
           │                                       ▼
           │                            ┌──────────────────┐
           │                            │  Inngest Worker  │
           │                            │  (Functions)     │
           │                            └────────┬─────────┘
           │                                     │
           │        Webhook Callback            │
           ◀────────────────────────────────────┘
```

### Setting Up Inngest in Production

1. **Create an Inngest Account**:
   - Sign up at [inngest.com](https://www.inngest.com/)
   - Create a new application in the Inngest dashboard

2. **Configure Environment Variables**:
   Set these variables in your production environment (e.g., Render.com):

   ```
   INNGEST_URL=https://api.inngest.com/e/yourappkey
   INNGEST_ENABLED=true
   INNGEST_FUNCTION_NAME=get-artist
   FLASK_WEBHOOK_URL=https://your-app.onrender.com/webhook/artist-result
   ```

3. **Deploy the Inngest Worker**:
   You need to deploy the Inngest worker alongside your Flask app:

   - Option 1: Deploy as a separate service on Render:
     ```
     uvicorn inngest.inngest_app:app --host 0.0.0.0 --port $PORT
     ```

   - Option 2: Integrate directly with Inngest Cloud:
     - Add Inngest as a provider in your Inngest dashboard
     - Deploy your functions to Inngest directly

### Testing Inngest Integration

To test if Inngest is properly configured:

1. Try an artist search in the UI
2. Check the logs to ensure events are being sent to Inngest
3. Verify the webhook is receiving responses
4. Confirm results are displayed in the UI

### Debugging Inngest Issues

- **Check Application Logs**: Look for errors in both Flask app and Inngest worker logs
- **Inspect Inngest Dashboard**: View events and function executions
- **Test Webhook Endpoint**: Ensure `/webhook/artist-result` is accessible
- **Verify Environment Variables**: Make sure INNGEST_URL is correctly configured

### Scaling Considerations

- Inngest functions run on a serverless infrastructure that scales automatically
- The application can handle many concurrent requests without blocking
- For very high traffic, consider Redis or another distributed cache for RECENT_ARTIST_RESULTS

### Local Development with Inngest

For local development:

1. Install Inngest CLI:
   ```
   npm install -g inngest
   ```

2. Run the dev server (in a separate terminal):
   ```
   inngest dev
   ```

3. Set the local environment variables:
   ```
   INNGEST_URL=http://localhost:8288/e
   INNGEST_ENABLED=true
   FLASK_WEBHOOK_URL=http://localhost:5000/webhook/artist-result
   ```

4. Run your application and Inngest functions:
   ```
   # Terminal 1: Flask app
   python app.py
   
   # Terminal 2: Inngest worker
   uvicorn inngest.inngest_app:app --reload
   ``` 