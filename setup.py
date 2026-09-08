"""
Interactive setup script for Discrete Math Problem Checker.

Creates the local, gitignored config files the app reads at runtime
(key.txt, config.txt) that aren't included in the git repo, and checks
that the ad hoc runtime dependencies (pandas, cryptography) are installed.

Run with:
    python3 setup.py
"""
import importlib.util
import re
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
QUESTION_MANAGER = REPO_ROOT / "questionManager.py"
DEFAULT_HOMEWORK_IDS = ["1b", "2", "3", "4", "5"]


def prompt(question, default=None):
    suffix = f" [{default}]" if default is not None else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer or default


def confirm_overwrite(path):
    answer = input(f"{path.name} already exists. Overwrite it? [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def discover_homework_ids():
    """Read the homework IDs straight out of questionManager.py's source,
    so this stays in sync without importing a module that needs pandas/
    cryptography to already be installed."""
    try:
        text = QUESTION_MANAGER.read_text()
    except OSError:
        return DEFAULT_HOMEWORK_IDS
    ids = re.findall(r'HomeworkSet\(\s*"([^"]+)"', text)
    return ids or DEFAULT_HOMEWORK_IDS


def setup_key_file():
    path = REPO_ROOT / "key.txt"
    if path.exists() and not confirm_overwrite(path):
        print(f"Skipping {path.name}.")
        return

    print(
        "\nkey.txt holds a passphrase that's SHA-256 hashed into a Fernet key "
        "for encrypting question fingerprints in cookies (not a security "
        "boundary, just an anti-cheat deterrent)."
    )
    passphrase = prompt("Enter a passphrase (blank to generate a random one)")
    if not passphrase:
        passphrase = secrets.token_urlsafe(32)
        print("Generated a random passphrase.")

    path.write_text(passphrase)
    print(f"Wrote {path.name}.")


def setup_config_file():
    path = REPO_ROOT / "config.txt"
    if path.exists() and not confirm_overwrite(path):
        print(f"Skipping {path.name}.")
        return

    homework_ids = discover_homework_ids()
    print(f"\nconfig.txt selects the active homework set. Known IDs: {', '.join(homework_ids)}")
    default_id = homework_ids[-1]
    while True:
        homework_id = prompt("Active homework ID", default=default_id)
        if homework_id in homework_ids:
            break
        confirm = input(
            f"'{homework_id}' isn't one of the known IDs ({', '.join(homework_ids)}). Use it anyway? [y/N]: "
        ).strip().lower()
        if confirm in ("y", "yes"):
            break

    path.write_text(f"HOMEWORK:{homework_id}\n")
    print(f"Wrote {path.name}.")


def check_dependencies():
    missing = [pkg for pkg in ("pandas", "cryptography") if importlib.util.find_spec(pkg) is None]
    if missing:
        print(f"\nMissing runtime dependencies: {', '.join(missing)}")
        print(f"Install with: {sys.executable} -m pip install {' '.join(missing)}")
    else:
        print("\nRuntime dependencies (pandas, cryptography) are already installed.")


def main():
    print("Discrete Math Problem Checker: Boolhound edition setup\n" + "=" * 36)
    setup_key_file()
    setup_config_file()
    check_dependencies()
    print("\nDone. Run the app with: python3 wsgi_backend.py")


if __name__ == "__main__":
    main()
