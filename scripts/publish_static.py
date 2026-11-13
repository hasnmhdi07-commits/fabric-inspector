"""Publish (or update) the in-browser app (web_static/) as a FREE static Hugging Face Space.
Needs the token in C:\\thesis\\hf_token.txt.  Usage: python scripts\\publish_static.py [space-name]
"""
import sys
from pathlib import Path
from huggingface_hub import HfApi

TOKEN = Path(r"C:\thesis\hf_token.txt").read_text().strip()
FOLDER = Path(r"C:\thesis\web_static")
name = sys.argv[1] if len(sys.argv) > 1 else "fabric-defect-inspector"

api = HfApi(token=TOKEN)
user = api.whoami()["name"]
repo = f"{user}/{name}"
api.create_repo(repo, repo_type="space", space_sdk="static", private=False, exist_ok=True)
api.upload_folder(folder_path=str(FOLDER), repo_id=repo, repo_type="space",
                  commit_message="Publish Fabric Defect Inspector (in-browser app)")
print("Space page:", f"https://huggingface.co/spaces/{repo}")
print("App link  :", f"https://{user.lower()}-{name.lower()}.static.hf.space")
