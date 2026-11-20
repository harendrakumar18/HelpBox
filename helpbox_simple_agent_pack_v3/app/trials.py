import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class TrialSecurityError(Exception):
    """Raised when a trial path or filename violates safety rules."""
    pass


class TrialNotFoundError(Exception):
    """Raised when a trial directory does not exist."""
    pass


def sanitize_and_validate_trial_name(trial_name: str, trials_root: Path) -> Path:
    """
    Validate that trial_name is a direct, safe child directory under trials_root.
    Rejects directory traversal (..), path separators, and out-of-root symlinks.
    """
    if not trial_name or not isinstance(trial_name, str):
        raise TrialSecurityError("Trial name cannot be empty.")

    # Disallow path separators, null bytes, quotes, semicolons, and traversal characters
    if any(c in trial_name for c in ("/", "\\", "\0", "'", '"', ";", "%")):
        raise TrialSecurityError("Invalid trial name: illegal characters detected.")

    if trial_name in {".", ".."}:
        raise TrialSecurityError("Invalid trial name: special directory references are not permitted.")

    resolved_root = trials_root.resolve()
    if not resolved_root.exists() or not resolved_root.is_dir():
        raise TrialNotFoundError(f"Trials root directory does not exist: {resolved_root}")

    trial_path = (resolved_root / trial_name).resolve()

    # Must be a direct child of the resolved root
    if trial_path.parent != resolved_root:
        raise TrialSecurityError("Access denied: trial folder must be a direct child of the trials root.")

    # Must stay within the resolved root
    try:
        trial_path.relative_to(resolved_root)
    except ValueError:
        raise TrialSecurityError("Access denied: path traversal detected.")

    # Check symlinks: target must stay inside trials root
    real_path = Path(os.path.realpath(trial_path))
    try:
        real_path.relative_to(resolved_root)
    except ValueError:
        raise TrialSecurityError("Access denied: symlink escapes trials root.")

    if not trial_path.exists() or not trial_path.is_dir():
        raise TrialNotFoundError(f"Trial '{trial_name}' not found.")

    return trial_path


def list_trial_folders(trials_root: Path) -> List[str]:
    """
    List only safe direct child trial folders under trials_root.
    """
    resolved_root = trials_root.resolve()
    if not resolved_root.exists() or not resolved_root.is_dir():
        return []

    trials = []
    for entry in sorted(resolved_root.iterdir()):
        # Skip hidden files/folders (e.g. .gitkeep)
        if entry.name.startswith("."):
            continue

        if not entry.is_dir():
            continue

        # Prevent symlink escapes
        real_path = Path(os.path.realpath(entry))
        try:
            real_path.relative_to(resolved_root)
        except ValueError:
            # Symlink escapes root; skip safely
            continue

        trials.append(entry.name)

    return sorted(trials)


def compute_file_sha256(file_path: Path) -> str:
    """
    Compute SHA-256 hash of a file opened read-only.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


SUPPORTED_EXTENSIONS = (".pdf", ".docx")


def list_trial_pdfs(trial_name: str, trials_root: Path, compute_hashes: bool = False) -> List[Dict[str, Any]]:
    """
    List direct-child PDF and DOCX files inside the validated trial folder.
    Never modifies source files. Does not recurse into subdirectories.
    """
    trial_path = sanitize_and_validate_trial_name(trial_name, trials_root)
    resolved_root = trials_root.resolve()

    pdf_files: List[Dict[str, Any]] = []

    for entry in sorted(trial_path.iterdir()):
        # Skip hidden files
        if entry.name.startswith("."):
            continue

        # Only direct files ending in supported extensions (case-insensitive: .pdf, .docx)
        if not entry.is_file() or not any(entry.name.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
            continue

        # Prevent symlinks escaping root
        real_path = Path(os.path.realpath(entry))
        try:
            real_path.relative_to(resolved_root)
        except ValueError:
            continue

        stat = entry.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

        doc_info: Dict[str, Any] = {
            "filename": entry.name,
            "relative_path": entry.name,
            "size_bytes": stat.st_size,
            "modified_at": mtime,
            "status": "DISCOVERED",
        }

        if compute_hashes:
            doc_info["sha256"] = compute_file_sha256(entry)

        pdf_files.append(doc_info)

    return pdf_files
