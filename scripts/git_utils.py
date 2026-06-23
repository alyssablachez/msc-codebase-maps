import subprocess


def git(repo_dir, args, check=True):
    return subprocess.run(
        ["git", "-C", repo_dir] + args,
        capture_output=True, text=True, check=check,
    )


def current_head(repo_dir):
    return git(repo_dir, ["rev-parse", "HEAD"]).stdout.strip()


def checkout(repo_dir, commit):
    git(repo_dir, ["checkout", "--detach", commit])


def restore(repo_dir, original_head):
    git(repo_dir, ["checkout", original_head])
