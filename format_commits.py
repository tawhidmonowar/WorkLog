import os
import requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from google import genai

GITHUB_TOKEN = os.getenv("GH_PATH")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

USERNAME = os.getenv("GH_USERNAME")
TARGETS = [t.strip() for t in os.getenv("GH_TARGETS", "").split(",") if t.strip()]

def get_since_time():
    bd_timezone = timezone(timedelta(hours=6))
    now_bd = datetime.now(bd_timezone)

    start_bd = now_bd.replace(hour=8, minute=0, second=0, microsecond=0)

    if now_bd < start_bd:
        start_bd -= timedelta(days=1)

    start_utc = start_bd.astimezone(timezone.utc)

    return start_utc.isoformat().replace("+00:00", "Z")

def is_target_repo(repo_full_name):
    owner = repo_full_name.split("/")[0].lower()
    return owner in [t.lower() for t in TARGETS]


def is_valid_commit(message):
    msg = message.lower()
    return not (
        msg.startswith("merge") or
        msg.startswith("revert")
    )

def fetch_commits_page(page, since_time):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.cloak-preview"
    }

    query = f"author:{USERNAME} committer-date:>={since_time}"

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

def fetch_events_commits():
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    url = f"https://api.github.com/users/{USERNAME}/events"
    response = requests.get(url, headers=headers)
    events = response.json()

    if not isinstance(events, list):
        return []

    since_time = get_since_time()
    since_dt = datetime.fromisoformat(since_time.replace("Z", "+00:00"))

    commits = []

    for event in events:
        if event["type"] != "PushEvent":
            continue

        event_time = datetime.strptime(
            event["created_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)

        if event_time < since_dt:
            continue

        repo = event["repo"]["name"]

        if not is_target_repo(repo):
            continue

        for c in event["payload"].get("commits", []):
            commits.append({
                "sha": c["sha"],
                "repo": repo,
                "message": c["message"]
            })

    return commits

def get_recent_commits():
    since_time = get_since_time()

    seen = set()
    grouped = defaultdict(list)

    pages = [1, 2]

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(fetch_commits_page, p, since_time)
            for p in pages
        ]

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

    events_commits = fetch_events_commits()

    for c in events_commits:
        if c["sha"] in seen:
            continue

        message = c["message"].splitlines()[0]

        if not is_valid_commit(message):
            continue

        grouped[c["repo"]].append(message)
        seen.add(c["sha"])

    return grouped

def format_commits(grouped):
    if not grouped:
        return ""

    formatted = ""

    for repo, messages in grouped.items():
        formatted += f"\n[{repo}]\n"
        for msg in messages:
            formatted += f"- {msg}\n"

    return formatted

def send_to_slack(formatted_text):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
            Act as a senior software engineer writing a daily stand-up update.
            
            Rules:
            - Group by repository
            - Use bullet points
            - Keep it concise
            - Focus on meaningful work
            
            Commits:
            {formatted_text}
            """
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )

        message = response.text.strip()

    except Exception as e:
        print(f"Gemini failed: {e}")

        # Fallback if AI fails
        message = f"*Daily Work Status*\n\n{formatted_text}"
    requests.post(SLACK_WEBHOOK_URL, json={"text": message})

def main():
    grouped = get_recent_commits()

    if not grouped:
        print("No activity detected in target repos.")
        return

    formatted = format_commits(grouped)

    send_to_slack(formatted)

    print("Stand-up sent successfully.")


if __name__ == "__main__":
    main()

