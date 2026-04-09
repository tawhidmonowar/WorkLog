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
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.cloak-preview"
    }

    since_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    query = f"author:{USERNAME} committer-date:>={since_date}"

    url = "https://api.github.com/search/commits"
    params = {
        "q": query,
        "sort": "committer-date",
        "order": "desc",
        "per_page": 100
    }

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if "items" not in data:
        print(f"Error: {data}")
        return ""

    relevant_commits = []
    seen = set()

    for item in data["items"]:
        sha = item["sha"]
        if sha in seen:
            continue

        repo_name = item["repository"]["full_name"]
        message = item["commit"]["message"].splitlines()[0]

        relevant_commits.append(f"[{repo_name}] {message}")
        seen.add(sha)

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
