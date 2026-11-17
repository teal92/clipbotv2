"""Rules for newly chosen passwords only; never applied to legacy login checks."""
import re

_COMMON = re.compile(r'^(password|qwerty|letmein|welcome|admin|iloveyou|changeme)[0-9]*$')

def password_policy_errors(password: str) -> list[str]:
    if not isinstance(password, str):
        return ['Enter a password.']
    checks = [
        (12 <= len(password) <= 128, 'Use 12–128 characters.'),
        (bool(re.search(r'[A-Z]', password)), 'Add an uppercase letter (A–Z).'),
        (bool(re.search(r'[a-z]', password)), 'Add a lowercase letter (a–z).'),
        (bool(re.search(r'[0-9]', password)), 'Add a number (0–9).'),
        (bool(re.search(r'[^A-Za-z0-9\s]', password)), 'Add a special character, such as ! or @.'),
        (not _COMMON.fullmatch(re.sub(r'[^a-z0-9]', '', password.lower())), 'Avoid common passwords such as Password123!.'),
    ]
    return [message for passed, message in checks if not passed]

def validate_new_password(password: str) -> None:
    errors = password_policy_errors(password)
    if errors:
        raise ValueError(' '.join(errors))
