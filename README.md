# voice-ai-agent

Challenge: Voice AI Agent Using OpenAI Assistants SDK + Twilio + GCP

Goal:
Build a conversational AI voice agent powered by the OpenAI Assistants SDK and deployed via a FastAPI backend on Google Cloud. The agent should handle voice input from Twilio, respond conversationally, and store transcripts in GCS storage including audio files.

## Project Structure

```
voice-ai-agent
├── src
│   ├── api
│   ├── config
│   ├── core
│   ├── services
│   └── utils
├── tests
├── .env.example
├── main.py
├── requirements.txt
└── README.md
```

## Setup Instructions

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd voice-ai-agent
   ```

2. Create a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:

   - Copy `.env.example` to `.env` and fill in the required values.

5. Run the application:
   ```bash
   uvicorn main:app --reload
   ```

## Testing

To run the tests, use:

```bash
pytest
```

## License

This project is licensed under the MIT License.
