# PR Reviewer Recommendation System

This repository provides a collection of scripts and GitHub Actions workflows to automate the process of:
1. Storing pull request data (PRs, files, and reviews) in a local SQLite database.
2. Automatically labeling new PRs if they are missing labels.
3. Generating reviewer recommendations based on various signals (e.g. file paths, tags, dynamic activity, and feedback).
4. Allowing feedback to update reviewer “favorite” points.
5. Viewing reviewer data in an Excel export.

Below is an overview of each file’s purpose and how they fit together.

---

## Table of Contents

- [Configuration File](#configuration-file)
  - [config.ini](#configini)
- [Database Reset Script](#database-reset-script)
  - [delete_tables_restart.py](#delete_tables_restartpy)
- [Database File](#database-file)
  - [pr_data.db](#pr_datadb)
- [Scripts](#scripts)
  - [store_prs2.py](#store_prs2py)
  - [view_reviewer_data_excel.py](#view_reviewer_data_excelpy)
  - [ml_pm2_spda_fav_fs_t15_rr.py](#ml_pm2_spda_fav_fs_t15_rrpy)
  - [recommendation.py](#recommendationpy)
  - [process_feedback.py](#process_feedbackpy)
- [GitHub Workflows](#github-workflows)
  - [.github/workflows/post_recommendations.yml](#githubworkflowspost_recommendationsyml)
  - [.github/workflows/process_feedback.yml](#githubworkflowsprocess_feedbackyml)
  - [new-prs-labeler.yml](#new-prs-labeleryml)
  - [new-prs-labeler.yml (Alternate Explanation)](#new-prs-labeleryml-alternate-explanation)
- [Usage Workflow](#usage-workflow)
  - [1. Update the config.ini](#1-update-the-configini)
  - [2. Initialize or Update the Database](#2-initialize-or-update-the-database)
  - [3. (Optional) Reset the Database](#3-optional-reset-the-database)
  - [4. Run Recommendation or Other Scripts](#4-run-recommendation-or-other-scripts)
- [Feedback and Points](#feedback-and-points)
- [Excel Export](#excel-export)
- [Additional Notes](#additional-notes)

---

## Configuration File

### `config.ini`
This file holds configuration details that the scripts use to gather data from GitHub. The sections include:

- **[github]**  
  Contains your `token`, `owner`, and `repo`:
  - `token` is your personal access token (PAT) for GitHub. (Keep this secret!)
  - `owner` is the GitHub organization or user who owns the repository.
  - `repo` is the actual repository name.

- **[filters]**  
  Specifies date ranges, filtering options such as:
  - `start_date` and `end_date` for limiting which pull requests get retrieved.
  - `only_closed_prs`, `only_merged_prs`.
  - `required_labels` (can be left blank if no requirement).

- **[database]**  
  Points to the local SQLite database file (by default, `pr_data.db`).

> **Important**: Do **not** commit sensitive tokens to a public repository. The token in the example is just a placeholder.

---

## Database Reset Script

### `delete_tables_restart.py`
If you ever need to start over or clear data from the local database, run this script. It deletes all entries from these tables:
- `pr_files`
- `reviews`
- `pull_requests`
- `feedback`

This is useful if you want to wipe the database and rebuild from scratch.

---

## Database File

### `pr_data.db`
This is the SQLite database where all data is stored:
- **pull_requests**: Contains `pr_id`, `title`, `user_login`, `labels`, `created_at`, `updated_at`.
- **pr_files**: Holds the PR file paths mapped to a `pr_id`.
- **reviews**: Contains `pr_id`, `reviewer`, `review_date`, `state` (e.g., APPROVED, COMMENTED).
- **feedback**: Stores each reviewer’s favorite reviewer points (`fav_rev_points`), used to give certain reviewers a boost when they receive positive feedback.

If you have not created it yet, it will be generated by the scripts when needed.

---

## Scripts

### `store_prs2.py`
- **Purpose**: Uses the configuration (`config.ini`) to connect to GitHub’s API and fetch pull requests (and their associated files, reviews, etc.), storing them into `pr_data.db`.
- **Usage**: Run it in your terminal:
  ```bash
  python store_prs2.py
