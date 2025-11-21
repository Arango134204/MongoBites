import os
from dotenv import load_dotenv
from pymongo import MongoClient
import certifi

load_dotenv()
uri = os.getenv("MONGO_URI")
print("Probando conexión...")
client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=30000)
client.admin.command("ping")
print("✅ Conexión exitosa.")
