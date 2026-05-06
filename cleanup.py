import os
import shutil

# Target directory
TARGET_DIR = r"C:\Users\maazq\OneDrive\Desktop\Main proj\PaisaDouble"

# Whitelists
FOLDERS_TO_KEEP = {
    "src",
    "scripts",
    "assets",
    "output_videos",
    "Songs",
    "docs",
    "venv",
    ".git" # Also keep git
}

FILES_TO_KEEP = {
    "cron.py",
    "main.py",
    "config.py",
    "cache.py",
    "llm_provider.py",
    "utils.py",
    "art.py",
    "status.py",
    "constants.py",
    "test_gemini.py",
    "list_models.py",
    "config.json",
    "config.example.json",
    "containers.json",
    "out_img.json",
    ".gitignore",
    ".python-version",
    "AGENTS.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "cleanup.py",  # Keep this script itself
    "requirements.txt",
    "README.md",
    "ffmpeg.exe",
    "ffprobe.exe",
    ".vscode",
    "technical_breakdown.md",
}

def main():
    if not os.path.exists(TARGET_DIR):
        print(f"Error: Target directory does not exist: {TARGET_DIR}")
        return

    items_to_delete = []

    # Identify items to delete
    for item in os.listdir(TARGET_DIR):
        item_path = os.path.join(TARGET_DIR, item)
        if os.path.isdir(item_path):
            if item not in FOLDERS_TO_KEEP:
                items_to_delete.append(item_path)
        else:
            if item not in FILES_TO_KEEP:
                items_to_delete.append(item_path)

    if not items_to_delete:
        print("No unwhitelisted files or folders found. The directory is clean.")
        return

    print("--- DRY RUN: Items to be DELETED ---")
    for item_path in items_to_delete:
        print(f"DELETE: {item_path}")
    print("------------------------------------")
    print(f"Total items to delete: {len(items_to_delete)}")
    
    confirm = input("Do you want to proceed with deletion? (yes/no): ").strip().lower()
    
    if confirm in ['yes', 'y']:
        print("\nStarting deletion process...")
        for item_path in items_to_delete:
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"Deleted directory: {item_path}")
                else:
                    os.remove(item_path)
                    print(f"Deleted file: {item_path}")
            except Exception as e:
                print(f"Failed to delete {item_path}: {e}")
        print("Deletion complete.")
    else:
        print("Deletion cancelled.")

if __name__ == "__main__":
    main()
