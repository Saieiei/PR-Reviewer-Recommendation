import configparser
import requests
import sqlite3
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def load_config(config_file="config.ini"):
    config = configparser.ConfigParser()
    config.read(config_file)
    return config

def create_tables_if_needed(conn):
    """
    Create all required tables if they do not exist yet.
    """
    cursor = conn.cursor()

    # Create table: pull_requests
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pull_requests (
            pr_id INTEGER PRIMARY KEY,
            title TEXT,
            user_login TEXT,
            labels TEXT,
            created_at TEXT,
            updated_at TEXT
        );
    """)

    # Create table: pr_files
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pr_files (
            pr_id INTEGER,
            file_path TEXT
        );
    """)

    # Create table: reviews
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            pr_id INTEGER,
            reviewer TEXT,
            review_date TEXT,
            state TEXT
        );
    """)

    # Create table: feedback (added as per your screenshot)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            -- ROWID is automatically generated by SQLite
            reviewer TEXT,
            fav_rev_points INTEGER
        );
    """)

    conn.commit()

def fetch_prs_in_range(token, owner, repo,
                       start_date_str, end_date_str,
                       only_closed=False,
                       verify_ssl=True,
                       required_labels=None):
    """
    Fetches Pull Requests in a date range (start_date_str to end_date_str).
    If only_closed=True, only closed PRs are returned; else all states.
    If required_labels is set, only PRs having at least one of those labels are returned.
    """
    if required_labels is None:
        required_labels = []
    required_labels = set(lbl.lower() for lbl in required_labels)

    start_date = datetime.fromisoformat(start_date_str)
    end_date   = datetime.fromisoformat(end_date_str)

    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    })
    session.verify = verify_ssl

    retries = Retry(
        total=10,
        backoff_factor=1,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)

    all_prs = []
    page = 1
    per_page = 100

    while True:
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        pr_state = "closed" if only_closed else "all"
        params = {
            "state": pr_state,
            "sort": "created",
            "direction": "desc",
            "per_page": per_page,
            "page": page
        }

        try:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching PRs (page {page}): {e}")
            break

        pr_page = resp.json()
        if not pr_page:
            break

        for pr in pr_page:
            created_str = pr.get("created_at", "")
            if not created_str:
                continue
            created_dt = datetime.fromisoformat(created_str.replace("Z", ""))

            # Skip if PR is outside the date range
            if created_dt > end_date:
                continue
            elif created_dt < start_date:
                # Because results are in descending order, we can stop
                break

            # Filter by labels if required_labels is not empty
            if required_labels:
                label_objs = pr.get("labels", [])
                pr_label_names = set(lbl["name"].lower() for lbl in label_objs)
                if pr_label_names.isdisjoint(required_labels):
                    continue

            all_prs.append(pr)
        else:
            # Only reached if the for-loop didn't break
            page += 1
            continue
        break  # if the for-loop did break, we end the while-loop

    return all_prs

def fetch_pr_main_details(token, owner, repo, pr_number, verify_ssl=True):
    """
    Fetch the single PR object to check extra details like 'merged', 'merged_by', etc.
    Returns the JSON data or None if there's an error.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    })
    session.verify = verify_ssl

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching main PR details for #{pr_number}: {e}")
        return None

def fetch_commits_for_pr(token, owner, repo, pr_number, verify_ssl=True):
    """
    Fetch commits for a PR. We'll store commit authors in 'reviews' with state='COMMIT'.
    """
    commits_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/commits"
    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    })
    session.verify = verify_ssl

    retries = Retry(
        total=10,
        backoff_factor=1,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)

    all_commits = []
    page = 1
    per_page = 100

    while True:
        params = {"per_page": per_page, "page": page}
        try:
            r = session.get(commits_url, params=params, timeout=30)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching commits for PR #{pr_number}: {e}")
            break

        commit_page = r.json()
        if not commit_page:
            break

        all_commits.extend(commit_page)
        if len(commit_page) < per_page:
            break
        page += 1

    return all_commits

def fetch_pr_details(token, owner, repo, pr_number, verify_ssl=True):
    """
    Fetch changed files and reviews for a single pull request.
    """
    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    })
    session.verify = verify_ssl

    retries = Retry(
        total=10,
        backoff_factor=1,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)

    # 1) PR files
    files_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    all_files = []
    page = 1
    per_page = 100
    while True:
        params = {"per_page": per_page, "page": page}
        try:
            r = session.get(files_url, params=params, timeout=30)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching files for PR #{pr_number}: {e}")
            break

        file_page = r.json()
        if not file_page:
            break

        all_files.extend(file_page)
        if len(file_page) < per_page:
            break
        page += 1

    # 2) PR reviews
    reviews_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    all_reviews = []
    page = 1
    while True:
        params = {"per_page": per_page, "page": page}
        try:
            r = session.get(reviews_url, params=params, timeout=30)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching reviews for PR #{pr_number}: {e}")
            break

        review_page = r.json()
        if not review_page:
            break

        all_reviews.extend(review_page)
        if len(review_page) < per_page:
            break
        page += 1

    return all_files, all_reviews

def insert_data_into_db(conn, pr_list, token, owner, repo,
                        only_merged_prs=True, verify_ssl=True):
    """
    For each PR in pr_list, optionally check if it's merged (if only_merged_prs=True).
    Then insert PR details, commit authors, changed file paths, and reviews into the DB.
    """
    cursor = conn.cursor()

    for pr in pr_list:
        pr_number = pr["number"]
        main_pr_data = fetch_pr_main_details(token, owner, repo, pr_number, verify_ssl)
        if not main_pr_data:
            continue

        # If config says "only_merged_prs" and merged is false, skip
        if only_merged_prs and not main_pr_data.get("merged", False):
            continue

        pr_title = main_pr_data.get("title", "")
        user_login = main_pr_data["user"]["login"] if main_pr_data.get("user") else "unknown"

        label_objs = main_pr_data.get("labels", [])
        label_names = [label["name"] for label in label_objs]
        labels_str = ",".join(label_names)

        created_at = main_pr_data.get("created_at", "")
        updated_at = main_pr_data.get("updated_at", "")

        # Insert into pull_requests
        cursor.execute("""
            INSERT OR IGNORE INTO pull_requests (pr_id, title, user_login, labels, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (pr_number, pr_title, user_login, labels_str, created_at, updated_at))

        # 1) Fetch commits (store authors in reviews table as "COMMIT")
        commits_data = fetch_commits_for_pr(token, owner, repo, pr_number, verify_ssl)
        for commit_obj in commits_data:
            commit_author_login = None
            if commit_obj.get("author"):
                commit_author_login = commit_obj["author"].get("login", None)

            if commit_author_login:
                cursor.execute("""
                    INSERT INTO reviews (pr_id, reviewer, review_date, state)
                    VALUES (?, ?, ?, ?)
                """, (pr_number, commit_author_login, "", "COMMIT"))

        # 2) Fetch PR files & PR reviews
        files_data, reviews_data = fetch_pr_details(token, owner, repo, pr_number, verify_ssl=verify_ssl)

        # Insert file paths
        for f in files_data:
            file_path = f.get("filename", "")
            cursor.execute("""
                INSERT OR IGNORE INTO pr_files (pr_id, file_path) VALUES (?, ?)
            """, (pr_number, file_path))

        # Insert reviews (only final states, skip PENDING)
        for rv in reviews_data:
            state = rv.get("state", "").upper()
            reviewer = rv["user"]["login"] if rv.get("user") else "unknown"
            review_date = rv.get("submitted_at", "")
            if state in ["APPROVED", "COMMENTED", "CHANGES_REQUESTED", "DISMISSED"]:
                cursor.execute("""
                    INSERT INTO reviews (pr_id, reviewer, review_date, state)
                    VALUES (?, ?, ?, ?)
                """, (pr_number, reviewer, review_date, state))

    conn.commit()

def main():
    """
    Main execution flow:
      1) Load config (token, owner, repo, date filters, etc.)
      2) Connect to SQLite DB and ensure tables exist
      3) Fetch PRs within date range
      4) Insert all relevant PR data into DB
    """
    # 1) Load config
    config = load_config("config.ini")

    # 2) Extract config values
    GITHUB_TOKEN = config["github"]["token"].strip()
    OWNER = config["github"]["owner"].strip()
    REPO = config["github"]["repo"].strip()

    start_date = config["filters"]["start_date"].strip()
    end_date   = config["filters"]["end_date"].strip()

    # only_closed_prs from config
    only_closed_prs = config["filters"].getboolean("only_closed_prs")

    # only_merged_prs (new param, default to True if not in config)
    if "only_merged_prs" in config["filters"]:
        only_merged_prs = config["filters"].getboolean("only_merged_prs")
    else:
        only_merged_prs = True

    required_labels = [
        lbl.strip()
        for lbl in config["filters"]["required_labels"].split(",")
        if lbl.strip()
    ]

    # 3) Database location
    DATABASE_FILE = config["database"]["file"].strip()

    # 4) Connect to DB and create tables
    conn = sqlite3.connect(DATABASE_FILE)
    create_tables_if_needed(conn)

    print(f"Fetching PRs from {start_date} to {end_date}, "
          f"only_closed={only_closed_prs}, labels={required_labels} ...")

    pr_list = fetch_prs_in_range(
        token=GITHUB_TOKEN,
        owner=OWNER,
        repo=REPO,
        start_date_str=start_date,
        end_date_str=end_date,
        only_closed=only_closed_prs,
        required_labels=required_labels,
        verify_ssl=True
    )
    print(f"Found {len(pr_list)} PRs matching date/label filters (closed={only_closed_prs}).")

    print(f"Storing data (only_merged_prs={only_merged_prs}) into the database...")
    insert_data_into_db(
        conn=conn,
        pr_list=pr_list,
        token=GITHUB_TOKEN,
        owner=OWNER,
        repo=REPO,
        only_merged_prs=only_merged_prs,
        verify_ssl=True
    )

    print("Done!")
    conn.close()

if __name__ == "__main__":
    main()
