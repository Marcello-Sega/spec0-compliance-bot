import os
import re
import requests
import subprocess
from datetime import datetime
from packaging.requirements import Requirement
from packaging.version import Version
import uuid
import toml
try:
    from github import Github
except ImportError:
    Github = None  # Let's do a dry-run

SPEC0_DEP_AGE_YEARS = 2
PYPI_URL = "https://pypi.org/pypi/{}/json"


def parse_requirements_txt(path):
    with open(path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def get_release_date(pkg_name, version):
    try:
        url = f"https://pypi.org/pypi/{pkg_name}/json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        version_str = str(Version(version))
        releases = data.get("releases", {})
        if version_str not in releases or not releases[version_str]:
            return None
        upload_info = releases[version_str][0]
        return datetime.fromisoformat(upload_info["upload_time_iso_8601"].rstrip("Z"))
    except Exception as e:
        print(f"Failed to get release date for {pkg_name}=={version}: {e}")
        return None


def get_latest_version(pkg_name):
    """
    Return the oldest version of the package still within the SPEC-0 support window (last 2 years).
    """
    try:
        url = f"https://pypi.org/pypi/{pkg_name}/json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        releases = data.get("releases", {})
        spec0_cutoff = datetime.now().timestamp() - (SPEC0_DEP_AGE_YEARS * 365.25 * 24 * 3600)

        # Collect (version, upload_time) pairs for versions within the support window
        compliant_versions = []
        for version_str, files in releases.items():
            if not files:
                continue
            try:
                upload_time = files[0].get("upload_time_iso_8601")
                if upload_time:
                    dt = datetime.fromisoformat(upload_time.rstrip("Z"))
                    if dt.timestamp() >= spec0_cutoff:
                        compliant_versions.append((Version(version_str), dt))
            except Exception:
                continue

        if compliant_versions:
            # Return the OLDEST version within the compliant window
            oldest = sorted(compliant_versions, key=lambda x: x[1])[0]
            return str(oldest[0])

        return None
    except Exception as e:
        print(f"Failed to get compliant version of {pkg_name}: {e}")
        return None


def is_outdated(release_date, max_years):
    return release_date and (datetime.now() - release_date).days / 365.25 > max_years

def extract_required_version(dep):
    try:
        req = Requirement(dep)
        for spec in req.specifier:
            if spec.operator in {">=", "=="}:
                return req.name, Version(spec.version)
        return req.name, None
    except Exception as e:
        print(f"Failed to parse {dep}: {e}")
        return None, None

def patch_requirements_file(path, outdated, dry_run=False):
    with open(path, "r") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            new_lines.append(line)
            continue

        updated = False
        for pkg, old_version, new_version in outdated:
            pattern = re.compile(rf"^{re.escape(pkg)}\s*([<>=!~]=?.*)?$")
            if pattern.match(stripped):
                new_line = f"{pkg}>={new_version}\n"
                print(f"{path}: {stripped} → {new_line.strip()}")
                new_lines.append(new_line)
                updated = True
                break

        if not updated:
            new_lines.append(line)

    if not dry_run:
        with open(path, "w") as f:
            f.writelines(new_lines)


def patch_pyproject_file(path, outdated, dry_run=False):
    with open(path, "r") as f:
        lines = f.readlines()

    def get_line_package(line):
        try:
            req = Requirement(line.strip().strip('",'))
            return req.name
        except Exception:
            return None

    new_lines = []
    inside_deps = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("dependencies = ["):
            inside_deps = True

        if inside_deps and stripped.startswith("]"):
            inside_deps = False

        if inside_deps and stripped:
            pkg = get_line_package(stripped)
            if pkg:
                replaced = False
                for name, old_version, new_version in outdated:
                    if pkg == name and old_version in line:
                        new_line = re.sub(r">=?\s*[\d\.a-zA-Z]+", f">={new_version}", line)
                        print(f"{path}: {line.strip()} → {new_line.strip()}")
                        new_lines.append(new_line)
                        replaced = True
                        break
                if not replaced:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if not dry_run:
        with open(path, "w") as f:
            f.writelines(new_lines)


def patch_setup_py(path, outdated, dry_run=False):
    with open(path, "r") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        updated = False
        for pkg, old_version, new_version in outdated:
            pattern = re.compile(rf"{re.escape(pkg)}\s*[<>=!~]=?\s*{re.escape(old_version)}")
            if pattern.search(line):
                new_line = pattern.sub(f"{pkg}>={new_version}", line)
                print(f"{path}: {line.strip()} → {new_line.strip()}")
                new_lines.append(new_line)
                updated = True
                break
        if not updated:
            new_lines.append(line)

    if not dry_run:
        with open(path, "w") as f:
            f.writelines(new_lines)


def commit_and_open_pr(branch="spec0-update", base="main", message="Update outdated dependencies (SPEC-0)", dry_run=False):
    if dry_run:
        print("Dry run mode: skipping git and PR creation.")
        return

    subprocess.run(["git", "config", "--global", "user.email", "spec0-bot@users.noreply.github.com"])
    subprocess.run(["git", "config", "--global", "user.name", "spec0-bot"])
    subprocess.run(["git", "checkout", "-b", branch])
    subprocess.run(["git", "add", "requirements.txt"])
    subprocess.run(["git", "commit", "-m", message])
    subprocess.run(["git", "push", "origin", branch])

    if not Github:
        print("PyGithub is not installed; cannot open PR.")
        return

    token = os.getenv("GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPOSITORY")
    if not token or not repo_name:
        print("Missing GITHUB_TOKEN or GITHUB_REPOSITORY.")
        try: print(token)
        except: print('missing token')
        try: print(repo_name)
        except: print('missing name')
        return

    gh = Github(token)
    repo = gh.get_repo(repo_name)
    pr = repo.create_pull(
        title=message,
        body="Automatically opened by SPEC-0 compliance bot.",
        head=branch,
        base=base,
    )
    print(f"Pull request created: {pr.html_url}")

def main(dry_run=False):
    print("Checking for SPEC-0 violations...\n")

    path = "requirements.txt"
    if not os.path.exists(path):
        print("requirements.txt not found.")
        return

    deps = parse_requirements_txt(path)
    outdated_pkgs = []

    for dep in deps:
        pkg, required_version = extract_required_version(dep)
        if not pkg or not required_version:
            continue

        release_date = get_release_date(pkg, str(required_version))
        if release_date and is_outdated(release_date, SPEC0_DEP_AGE_YEARS):
            latest = get_latest_version(pkg)
            if latest:
                outdated_pkgs.append((pkg, str(required_version), latest))
                print(f"{pkg} >= {required_version} (released {release_date.date()}), oldest SPEC-0-compliant: {latest}")

    if not outdated_pkgs:
        print("All dependencies are within the SPEC-0 window.")
        return
    print("\nUpdating...\n")
    if os.path.exists("requirements.txt"):
        patch_requirements_file("requirements.txt", outdated_pkgs, dry_run=dry_run)
    if os.path.exists("pyproject.toml"):
        patch_pyproject_file("pyproject.toml", outdated_pkgs, dry_run=dry_run)
    if os.path.exists("setup.py"):
        patch_setup_py("setup.py", outdated_pkgs, dry_run=dry_run)

    branch = f"spec0-update-{uuid.uuid4().hex[:6]}"
    commit_and_open_pr(branch=branch, dry_run=dry_run)

if __name__ == "__main__":
    dry = os.getenv("SPEC0_DRY_RUN", "true").lower() == "true"
    main(dry_run=dry)

