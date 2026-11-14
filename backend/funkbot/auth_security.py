"""Small security helpers shared by the single-user authentication endpoints."""
import os
import secrets
from pathlib import Path


def ensure_setup_token(data_dir: Path) -> str:
    """Create once per installation, without putting the setup code in SQLite."""
    path = data_dir / 'setup.token'
    token = secrets.token_urlsafe(32)
    try:
        # Exclusive creation avoids replacing a code another process is using.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text(encoding='utf-8').strip()
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write(token)
    return token


def lockout_seconds(failures: int) -> int:
    """After five failures, increase the lockout up to five minutes."""
    return 0 if failures < 5 else min(300, 2 ** min(failures - 4, 9))
