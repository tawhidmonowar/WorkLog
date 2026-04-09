import os
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from google import genai

GITHUB_TOKEN = os.getenv("GH_PATH")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

USERNAME = os.getenv("GH_USERNAME")
TARGETS = [t.strip() for t in os.getenv("GH_TARGETS", "").split(",") if t.strip()] 

def is_target_repo(repo_full_name):
    owner = repo_full_name.split("/")[0].lower()
    return owner in [t.lower() for t in TARGETS]

def is_valid_commit(message):
    msg = message.lower()
    return not (
        msg.startswith("merge") or
        msg.startswith("revert")
    )

def fetch_commits_page(page):
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
        "per_page": 100,
        "page": page
    }

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if "items" not in data:
        return []

    return data["items"]

def get_recent_commits():
    seen = set()
    grouped = defaultdict(list)

    pages = [1, 2, 3]

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_commits_page, p) for p in pages]

        for future in as_completed(futures):
            items = future.result()

            for item in items:
                repo = item["repository"]["full_name"]

                if not is_target_repo(repo):
                    continue

                sha = item["sha"]
                if sha in seen:
                    continue

                message = item["commit"]["message"].splitlines()[0]

                if not is_valid_commit(message):
                    continue

                grouped[repo].append(message)
                seen.add(sha)

    return grouped

def format_commits(grouped):
    if not grouped:
        return ""

    formatted = ""
    for repo, messages in grouped.items():
        formatted += f"\n[{repo}]\n"
        for m in messages:
            formatted += f"- {m}\n"

    return formatted

def send_to_slack(formatted_text):
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
Act as a senior software engineer writing a daily stand-up update.

Rules:
- Group by repository
- Use bullet points
- Dont use emoji
- Keep it concise but professional
- Focus on meaningful work (ignore trivial commits)

Commits:
{formatted_text}
"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )

    message = response.text.strip()

    slack_data = {
        "text": f"*Daily Work Status*\n\n{message}"
    }

    requests.post(SLACK_WEBHOOK_URL, json=slack_data)

def main():
    grouped = get_recent_commits()

    if not grouped:
        print("No activity detected in target repos.")
        return

    formatted = format_commits(grouped)
    send_to_slack(formatted)

    print("Standup sent to Slack!")

if __name__ == "__main__":
    main()
