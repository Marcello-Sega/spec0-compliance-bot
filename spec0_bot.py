import os
import re
import toml
import requests
from datetime import datetime
from packaging.requirements import Requirement
from packaging.version import Version, InvalidVersion

SPEC0_DEP_AGE_YEARS = 2
PYPI_URL = "https://pypi.org/pypi/{}/json"

def parse_requirements_txt(path):
    with open(path) as f:
        return [Requirement(line.strip()).name for line in f if line.strip() and not line.startswith("#")]

def parse_pyproject(path):
    try:
        deps = toml.load(path).get("project", {}).get("dependencies", [])
        return [Requirement(d).name for d in deps]
    except Exception:
        return []

def parse_setup_py(path):
    deps = []
    with open(path) as f:
        for line in f:
            match = re.search(r'["\']([a-zA-Z0-9\-_]+)[=<>!~]?[^"\']*["\']', line)
            if match:
                deps.append(match.group(1))
    return deps

def get_latest_release_date(pkg):
    try:
        r = requests.get(PYPI_URL.format(pkg))
        r.raise_for_status()
        data = r.json()
        version = data["info"]["version"]
        releases = data["releases"].get(version, [])
        if releases:
            return datetime.fromisoformat(releases[0]["upload_time_iso_8601"].rstrip("Z"))
    except Exception as e:
        print(f"Error checking {pkg}: {e}")
    return None

def is_outdated(release_date, max_years):
    return release_date and (datetime.now() - release_date).days / 365.25 > max_years

def main():
    print("🔍 Checking for SPEC-0 violations...\n")
    files = ["requirements.txt", "setup.py", "pyproject.toml"]
    all_deps = set()

    if os.path.exists("requirements.txt"):
        all_deps.update(parse_requirements_txt("requirements.txt"))
    if os.path.exists("setup.py"):
        all_deps.update(parse_setup_py("setup.py"))
    if os.path.exists("pyproject.toml"):
        all_deps.update(parse_pyproject("pyproject.toml"))

    violations = []
    for pkg in sorted(all_deps):
        date = get_latest_release_date(pkg)
        if is_outdated(date, SPEC0_DEP_AGE_YEARS):
            violations.append((pkg, date.date() if date else "unknown"))

    if violations:
        print("⚠️ Outdated dependencies (per SPEC-0):")
        for pkg, date in violations:
            print(f"  - {pkg} (latest release: {date})")
    else:
        print("✅ All dependencies are within the SPEC-0 window.")

if __name__ == "__main__":
    main()
