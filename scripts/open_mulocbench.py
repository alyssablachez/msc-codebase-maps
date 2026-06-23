import pickle
import collections

with open('data/all_issues_with_pr_commit_comment_all_project_0922.pkl', 'rb') as f:
    issues = pickle.load(f)

repos = collections.Counter(i['repo_name'] for i in issues)
for repo, count in sorted(repos.items(), key=lambda x: -x[1]):
    print(f"{repo}: {count} issues")