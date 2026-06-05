import os
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from onboarding import ping_cluster

load_dotenv()
uri = os.environ["MONGO_URI"]

client = MongoClient(uri, server_api=ServerApi('1'))

try:
    ping_cluster(client)
except Exception as e:
    print(e)