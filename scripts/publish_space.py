"""Publish (or update) the web app on Hugging Face Spaces.
Needs a Hugging Face WRITE token saved (one line) in C:\\thesis\\hf_token.txt
Usage: python scripts\\publish_space.py <space-name> [--private]
"""
import sys
from pathlib import Path
from huggingface_hub import HfApi

TOKEN = Path(r"C:\thesis\hf_token.txt").read_text().strip()
FOLDER = Path(r"C:\thesis\deploy\hf_space")
name = sys.argv[1] if len(sys.argv) > 1 else "fabric-defect-inspector"
private = "--private" in sys.argv

api = HfApi(token=TOKEN)
user = api.whoami()["name"]
repo = f"{user}/{name}"
api.create_repo(repo, repo_type="space", space_sdk="gradio", private=private, exist_ok=True)
api.upload_folder(folder_path=str(FOLDER), repo_id=repo, repo_type="space",
                  commit_message="Publish Fabric Defect Inspector")
print("Space page :", f"https://huggingface.co/spaces/{repo}")
print("App link   :", f"https://{user.lower()}-{name.lower()}.hf.space".replace("_", "-"))
print("Visibility :", "PRIVATE (only you)" if private else "PUBLIC (anyone with the link)")
