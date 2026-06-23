import pickle

with open('data/all_issues_with_pr_commit_comment_all_project_0922.pkl', 'rb') as f:
    issues = pickle.load(f)

# Look at one flask issue in full
flask_issues = [i for i in issues if i['repo_name'] == 'flask']
issue = flask_issues[0]

for key, value in issue.items():
    print(f"\n=== {key} ===")
    print(repr(value)[:300])