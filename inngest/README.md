# Inngest Worker for Chatbot Project

This directory contains the Inngest worker functions that handle background processing for the chatbot application.

## Overview

The Inngest worker is responsible for processing artist information requests asynchronously, which:

- Prevents blocking the main Flask application
- Allows for more complex database queries
- Provides better error handling and retries
- Improves user experience

## Directory Structure

```
inngest/
├── functions/          # Contains all Inngest functions
│   └── get_artist.py   # Artist lookup function
├── inngest_app.py      # FastAPI application that registers functions
└── README.md           # This file
```

## How It Works

1. The Flask app sends an event to Inngest with the artist name
2. Inngest queues the event and triggers the `get_artist` function
3. The function queries the database for artist details
4. Results are sent back to Flask via a webhook to `/webhook/artist-result`
5. The Flask app can then serve this information to the user

## Deploying to Render.com

### 1. Create a New Web Service

- Log in to Render.com
- Click "New" -> "Web Service"
- Connect your GitHub repository

### 2. Configure the Service

Use these settings:
- **Name**: `your-app-inngest-worker`
- **Runtime**: Python 3.9 or higher
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `cd inngest && uvicorn inngest_app:app --host 0.0.0.0 --port $PORT`

### 3. Environment Variables

Add these environment variables:
- `FLASK_WEBHOOK_URL`: URL to your Flask app's webhook (e.g., `https://your-app.onrender.com/webhook/artist-result`)
- `CHINOOK_DB_PATH`: Path to your SQLite database (if needed)

### 4. Advanced Configuration (Optional)

- Enable auto-deployments from GitHub
- Set up health checks (Endpoint: `/health` or `/`)
- Configure resource scaling based on your needs

## Deploying to Inngest Cloud

For production applications, you can use Inngest Cloud for improved reliability:

1. Sign up at [inngest.com](https://www.inngest.com/)
2. Connect your GitHub repository
3. Configure the deployment settings
4. Update your Flask app's `INNGEST_URL` to the provided URL

## Local Development

To run the Inngest worker locally:

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Install Inngest CLI:
   ```
   npm install -g inngest
   ```

3. Run the Inngest dev server:
   ```
   inngest dev
   ```

4. Run the FastAPI application:
   ```
   cd inngest
   uvicorn inngest_app:app --reload --port 8000
   ```

5. Set the Flask app's environment variables:
   ```
   INNGEST_URL=http://localhost:8288/e
   FLASK_WEBHOOK_URL=http://localhost:5000/webhook/artist-result
   ```

## Troubleshooting

- **Function not triggering**: Check the event name matches `get-artist`
- **Database errors**: Verify the Chinook.db file is accessible
- **Webhook failures**: Ensure the Flask app is running and accessible
- **401 Errors**: Check your Inngest API keys if using Inngest Cloud

## Additional Resources

- [Inngest Documentation](https://www.inngest.com/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Render Deployment Guide](https://render.com/docs/deploy-to-render) 