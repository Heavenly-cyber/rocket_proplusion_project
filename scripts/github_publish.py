"""Publish saved tags without credentials in the repo, logs, or containers."""

import json
import re
import zipfile

from host_common import ProjectError, folder, safe, sha, stamp, write_json

OWNER = "Heavenly-Cyber"
REPOSITORY = OWNER + "/rocket_proplusion_project"
URL = "https://github.com/" + REPOSITORY + ".git"
TAGS = ["v0.1.0", "v0.2.0", "v0.3.0"]


def remote_transport(url):
    """Accept only the intended GitHub repository, via HTTPS or SSH."""
    path = REPOSITORY.casefold()
    candidate = url.casefold()
    for suffix in (path, path + ".git"):
        if candidate == "https://github.com/" + suffix:
            return "https"
        if candidate in {"git@github.com:" + suffix, "ssh://git@github.com/" + suffix}:
            return "ssh"
    raise ProjectError("Existing origin targets another repository or unsupported URL; it was preserved.")


def checked_origin(runner):
    code, output = runner.run(["git", "remote", "get-url", "--all", "origin"], check=False, logged=False)
    if code:
        code, remotes = runner.run(["git", "remote"], check=False, logged=False)
        if code or "origin" in remotes.splitlines():
            raise ProjectError("Could not inspect existing origin; Git configuration was preserved.")
        return False
    urls = output.splitlines()
    code, pushes = runner.run(["git", "remote", "get-url", "--push", "--all", "origin"], check=False, logged=False)
    if code or len(urls) != 1 or len(pushes.splitlines()) != 1:
        raise ProjectError("Origin must have one verifiable fetch URL and one push URL; it was preserved.")
    remote_transport(urls[0])
    remote_transport(pushes.strip())
    return True


def git_transport(runner):
    url = runner.git("remote", "get-url", "origin")
    push_url = runner.git("remote", "get-url", "--push", "origin")
    transports = {remote_transport(url), remote_transport(push_url)}
    prefix = ["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
    if "ssh" in transports:
        # Per-command only: retain user's remote URL, keys, agent, and ~/.ssh/config.
        # Fail with a useful retry message rather than prompting inside a detached job.
        prefix += ["-c", "core.sshCommand=ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15"]
    return prefix, transports


def publish(runner):
    if runner.git("status", "--porcelain", "--untracked-files=all"):
        raise ProjectError("Save local Git changes before publishing.")
    if runner.git("cat-file", "-t", "refs/tags/v0.3.0") != "tag":
        raise ProjectError("Local Stage 03 verification and annotated v0.3.0 are required first.")
    if runner.git("rev-parse", "v0.3.0^{commit}") != runner.git("rev-parse", "HEAD"):
        raise ProjectError("Current HEAD differs from the completed Stage 03 tag; no publication attempted.")
    origin_exists = checked_origin(runner)
    code, account = runner.run(["gh", "api", "--hostname", "github.com", "user", "--jq", ".login"], check=False, logged=False)
    if code:
        print("GITHUB_AUTH_REQUIRED: choose Heavenly-Cyber in the local GitHub sign-in flow.", flush=True)
        runner.run(["gh", "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web"], interactive=True)
        _, account = runner.run(["gh", "api", "--hostname", "github.com", "user", "--jq", ".login"], logged=False)
    if account.strip().casefold() != OWNER.casefold():
        raise ProjectError("Active GitHub account is not Heavenly-Cyber. Local work is saved. Use gh auth switch --hostname github.com --user Heavenly-Cyber, then rerun.")
    code, record = runner.run(["gh", "api", "repos/" + REPOSITORY], check=False, logged=False)
    if code:
        if "HTTP 404" not in record:
            raise ProjectError("GitHub repository lookup failed; no repository was created.")
        runner.run(["gh", "repo", "create", REPOSITORY, "--private", "--description",
                    "Local LLM reliability for rocket nozzle performance: evidence, units, applicability"])
        _, record = runner.run(["gh", "api", "repos/" + REPOSITORY], logged=False)
    metadata = json.loads(record)
    if metadata["owner"]["login"].casefold() != OWNER.casefold() or not metadata.get("private"):
        raise ProjectError("Existing repository ownership/visibility differs; it was preserved.")
    if not origin_exists:
        runner.run(["git", "remote", "add", "origin", URL])
    # Credentials stay on the host; per-command settings never rewrite origin.
    git_prefix, transports = git_transport(runner)
    code, remote = runner.run(git_prefix + ["ls-remote", "origin"], check=False, logged=False, timeout=90)
    if code:
        transport_note = " Your SSH key/agent and GitHub host verification must work locally; test ssh -T git@github.com, then rerun publication." if "ssh" in transports else " Check gh auth status locally, then rerun publication."
        raise ProjectError("GitHub transport check failed; local commits and origin were preserved." + transport_note)
    refs = {line.split()[1]: line.split()[0] for line in remote.splitlines() if len(line.split()) == 2}
    if refs and "refs/heads/main" not in refs:
        raise ProjectError("The existing remote is not an empty repository and has no known main checkpoint; preserved.")
    if "refs/heads/main" in refs:
        remote_head = refs["refs/heads/main"]
        available = runner.run(["git", "cat-file", "-e", remote_head + "^{commit}"], check=False, logged=False)[0] == 0
        if not available or runner.run(["git", "merge-base", "--is-ancestor", remote_head, "HEAD"], check=False, logged=False)[0]:
            raise ProjectError("Remote main has unfamiliar/divergent history; no merge or overwrite was attempted.")
    for tag in TAGS:
        local_object = runner.git("rev-parse", "refs/tags/" + tag)
        if "refs/tags/" + tag in refs and refs["refs/tags/" + tag] != local_object:
            raise ProjectError("Remote tag conflict preserved: " + tag)
    runner.run(git_prefix + ["push", "--atomic", "--set-upstream", "origin", "HEAD:refs/heads/main",
                            *["refs/tags/" + tag + ":refs/tags/" + tag for tag in TAGS]], timeout=900)
    release_dir = folder("tmp/releases/" + stamp())
    for tag in TAGS:
        archive = release_dir / ("rocket_proplusion_project-" + tag + ".zip")
        runner.run(["git", "archive", "--format=zip", "--prefix=rocket_proplusion_project/",
                    "--output", str(archive), tag], logged=False)
        with zipfile.ZipFile(archive) as bundle:
            if any(re.search(r"(^|/)(models|cache|tmp)/|(^|/)\.env", name) for name in bundle.namelist()):
                raise ProjectError("Unexpected generated/private files in the release archive; preserved locally.")
        code, release = runner.run(["gh", "api", "repos/" + REPOSITORY + "/releases/tags/" + tag], check=False, logged=False)
        notes = safe("docs/releases/" + tag + ".md")
        if code:
            if "HTTP 404" not in release:
                raise ProjectError("Release lookup failed; existing remote state preserved.")
            args = ["gh", "release", "create", tag, str(archive), "--repo", REPOSITORY,
                    "--verify-tag", "--title", "RocketNozzle-LLM " + tag, "--notes-file", str(notes)]
            if tag != "v0.3.0":
                args.append("--latest=false")
            runner.run(args, timeout=900)
        else:
            previous = json.loads(release)
            asset = next((asset for asset in previous.get("assets", []) if asset["name"] == archive.name), None)
            if asset:
                if asset.get("digest") != "sha256:" + sha(archive.read_bytes()):
                    raise ProjectError("Existing release asset differs or has no verifiable digest; no replacement performed.")
            else:
                runner.run(["gh", "release", "upload", tag, str(archive), "--repo", REPOSITORY], timeout=900)
        print("RELEASE_PUBLISHED:", "https://github.com/" + REPOSITORY + "/releases/tag/" + tag)
    _, remote_head = runner.run(git_prefix + ["ls-remote", "origin", "refs/heads/main"], logged=False)
    if not remote_head.startswith(runner.git("rev-parse", "HEAD") + "\t"):
        raise ProjectError("Remote main verification failed; return the saved log.")
    write_json("logs/setup/github-publication.json", {"account": OWNER, "repository": REPOSITORY,
               "visibility": "private", "main_commit": runner.git("rev-parse", "HEAD"), "tags": TAGS,
               "url": "https://github.com/" + REPOSITORY, "publication_verified": True})
    print("GITHUB_STAGE_03_PUBLISHED:", "https://github.com/" + REPOSITORY)
