from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
uri = os.getenv("MONGO_URI")

print("Intentando conexión sin verificación TLS...")
client = MongoClient(uri, tls=True, tlsAllowInvalidCertificates=True)
print(client.admin.command("ping"))
print("✅ Conexión exitosa (sin verificación TLS)")
