import os
import requests
import google.generativeai as genai
from datetime import datetime, timedelta

GITHUB_TOKEN = os.getenv("GH_PATH")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

TARGETS = ["envobyte", "Envobyte-LTD"] 
USERNAME = "tawhidmonowar"

def get_recent_commits():
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    since_time = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
    relevant_commits = []
    seen_shas = set()

    repos = []

    for target in TARGETS:
        url = f"https://api.github.com/users/{target}/repos"
        response = requests.get(url, headers=headers)
        data = response.json()

        if isinstance(data, list):
            repos.extend([repo["full_name"] for repo in data])

    for repo in repos:
        commits_url = f"https://api.github.com/repos/{repo}/commits"
        params = {
            "author": USERNAME,
            "since": since_time
        }

        response = requests.get(commits_url, headers=headers, params=params)
        commits = response.json()

        if not isinstance(commits, list):
            continue

        for commit in commits:
            sha = commit["sha"]

            if sha in seen_shas:
                continue

            message = commit["commit"]["message"].splitlines()[0]
            repo_name = repo

            relevant_commits.append(f"[{repo_name}] {message}")
            seen_shas.add(sha)

    return "\n".join(relevant_commits)

def format_and_send():
    commit_history = get_recent_commits()
    
    if not commit_history:
        print("No activity detected today.")
        return

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3-flash-preview')
    
    prompt = f"""
    Act as a professional software engineer. Summarize my daily work based on these commits.
    - Group by repository.
    - Use bullet points.
    - Make it readable for a Slack stand-up channel.
    
    Commits:
    {commit_history}
    """
    
    try:
        response = model.generate_content(prompt)
        slack_data = {"text": f"*Daily Work Status*\n\n{response.text}"}
        requests.post(SLACK_WEBHOOK_URL, json=slack_data)
        print("Status sent to Slack successfully!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    format_and_send()
