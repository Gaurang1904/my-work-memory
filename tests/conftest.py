import os


os.environ["APP_ENV"] = "test"
os.environ["DEBUG"] = "true"
os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:postgres@localhost:5432/personal_doc_agent_test"
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["GEMINI_CHAT_MODEL"] = "gemini-2.5-flash"
os.environ["GEMINI_EMBEDDING_MODEL"] = "gemini-embedding-001"
os.environ["GEMINI_EMBEDDING_DIMENSIONS"] = "1536"
