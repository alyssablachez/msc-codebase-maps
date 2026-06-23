import pickle

with open('data/all_issues_with_pr_commit_comment_all_project_0922.pkl', 'rb') as f:
    issues = pickle.load(f)

flask_issues = [i for i in issues if i['repo_name'] == 'flask']

# print all flask issues to see what we have
for i, issue in enumerate(flask_issues):
    print(f"{i}: {issue['title']}")