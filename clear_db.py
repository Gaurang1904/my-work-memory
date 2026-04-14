import os
from sqlalchemy import create_engine, MetaData
from dotenv import load_dotenv

# Load the database URL from your .env file
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if __name__ == "__main__":
    print("Connecting to database...")
    engine = create_engine(DATABASE_URL)
    meta = MetaData()
    meta.reflect(bind=engine)
    meta.drop_all(bind=engine)
    print("Database cleared! All tables have been dropped.")
    print("You can now run your ingestion script to recreate the tables and re-embed your documents.")