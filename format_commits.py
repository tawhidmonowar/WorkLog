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
        "Accept": "application/vnd.github.v3+json"
    }
    
    url = f"https://api.github.com/users/{USERNAME}/events"
    response = requests.get(url, headers=headers)
    events = response.json()

    if not isinstance(events, list):
        print(f"Error fetching events: {events}")
        return ""

    since_time = datetime.utcnow() - timedelta(days=1)
    relevant_commits = []
    seen_shas = set() 

    for event in events:
        # 1. Filter by Time (Last 24 hours)
        event_date = datetime.strptime(event['created_at'], '%Y-%m-%dT%H:%M:%SZ')
        if event_date < since_time:
            continue

        if event['type'] == 'PushEvent':
            repo_name = event['repo']['name']
            owner = repo_name.split('/')[0]

            if owner.lower() in [t.lower() for t in TARGETS]:
                commits = event['payload'].get('commits', [])
                for commit in commits:
                    sha = commit['sha']
                    if sha not in seen_shas:
                        msg = f"[{repo_name}] {commit['message'].splitlines()[0]}"
                        relevant_commits.append(msg)
                        seen_shas.add(sha)

    return "\n".join(relevant_commits)

def format_and_send():
    commit_history = get_recent_commits()
    
    if not commit_history:
        print("No activity detected in the target profiles/orgs today.")
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
