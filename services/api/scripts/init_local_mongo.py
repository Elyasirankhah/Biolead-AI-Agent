from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=5000)
client.admin.command("ping")

db = client["biolead"]
db.runs.create_index("run_id", unique=True)
db.runs.create_index([("created_at", -1)])
db.meta.update_one(
    {"_id": "biolead"},
    {
        "$set": {
            "name": "BioLead Evidence Workbench",
            "purpose": "Stores analysis runs for local demo",
            "created_for": "biolead",
        }
    },
    upsert=True,
)

print("OK database:", db.name)
print("collections:", db.list_collection_names())
print("meta:", db.meta.find_one({"_id": "biolead"}))
