import os
import requests
import google.generativeai as genai
from datetime import datetime, timedelta

# Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# List targets here
TARGETS = ["envobyte", "Envobyte-LTD"] 
USERNAME = "tawhidmonowar" # GitHub handle

def get_commits():
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    # Look back 24 hours
    since = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
    all_messages = []

    for target in TARGETS:
        user_resp = requests.get(f"https://api.github.com/users/{target}", headers=headers).json()
        type_key = "orgs" if user_resp.get("type") == "Organization" else "users"
        
        repos_url = f"https://api.github.com/{type_key}/{target}/repos?type=private&per_page=100"
        repos = requests.get(repos_url, headers=headers).json()

        if not isinstance(repos, list):
            print(f"Could not access repos for {target}: {repos}")
            continue

        for repo in repos:
            repo_name = repo['name']
            commits_url = f"https://api.github.com/repos/{target}/{repo_name}/commits?author={USERNAME}&since={since}"
            commits = requests.get(commits_url, headers=headers).json()
            
            if isinstance(commits, list) and len(commits) > 0:
                for c in commits:
                    msg = c['commit']['message'].split('\n')[0]
                    all_messages.append(f"[{repo_name}] {msg}")
                
    return "\n".join(all_messages)

def format_and_send():
    raw_commits = get_commits()
    if not raw_commits:
        print("No activity found in the last 24 hours.")
        return

    # formatting logic
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    You are a professional assistant. Summarize these technical GitHub commits into 
    a clean, bulleted daily work status for a Slack channel. 
    Group by project and focus on achievements.
    
    Commits:
    {raw_commits}
    """
    
    response = model.generate_content(prompt)
    requests.post(SLACK_WEBHOOK_URL, json={"text": response.text})

if __name__ == "__main__":
    format_and_send()
