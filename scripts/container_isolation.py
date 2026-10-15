"""Inspect mount metadata without traversing another user's private directories."""

import re
from pathlib import PurePosixPath

SENSITIVE_TARGETS = tuple(PurePosixPath(name) for name in (
    "/var/run/docker.sock", "/run/docker.sock", "/app/.git", "/app/.env",
    "/root/.config/gh", "/root/.ssh", "/models",
))


def mount_points(text):
    """Read Linux mountinfo's escaped mount-point field; malformed input fails."""
    points = []
    for line in text.splitlines():
        if not line.strip():
            continue
        left, separator, right = line.partition(" - ")
        fields = left.split()
        if not separator or len(fields) < 6 or len(right.split()) < 3:
            raise ValueError("Invalid mountinfo record.")
        if not fields[0].isdigit() or not fields[1].isdigit() or not re.fullmatch(r"\d+:\d+", fields[2]):
            raise ValueError("Invalid mountinfo identity.")
        raw = fields[4]
        if "\\" in re.sub(r"\\[0-7]{3}", "", raw):
            raise ValueError("Invalid mountinfo escape.")
        decoded = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), raw)
        point = PurePosixPath(decoded)
        if not point.is_absolute() or ".." in point.parts or "\x00" in decoded:
            raise ValueError("Invalid mountinfo path.")
        points.append(point)
    if not points:
        raise ValueError("Mountinfo was empty.")
    return tuple(points)


def sensitive_mounts(text):
    """Find additional mounts exposing protected targets or their children.

    The normal root filesystem is expected. All other mount points are checked
    against protected paths, including ancestors such as /root or /app. This
    inspects mounts, not the contents of inaccessible directories.
    """
    return tuple(sorted({str(point) for point in mount_points(text)
                         if point != PurePosixPath("/") and any(
                             point.is_relative_to(target) or target.is_relative_to(point)
                             for target in SENSITIVE_TARGETS)}))
