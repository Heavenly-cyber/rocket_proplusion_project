"""Publication transport regression tests with a local, simulated GitHub adapter."""

from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SSH = "git@github.com:Heavenly-cyber/rocket_proplusion_project.git"
HEAD = "a" * 40


@contextmanager
def modules(root):
    previous = sys.modules.get("host_common")
    spec = importlib.util.spec_from_file_location("host_common", SCRIPTS / "host_common.py")
    common = importlib.util.module_from_spec(spec)
    sys.modules["host_common"] = common
    try:
        spec.loader.exec_module(common)
        common.ROOT = root
        spec = importlib.util.spec_from_file_location("remote_publication", SCRIPTS / "github_publish.py")
        publication = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publication)
        yield common, publication
    finally:
        if previous is None:
            sys.modules.pop("host_common", None)
        else:
            sys.modules["host_common"] = previous


class Adapter:
    def __init__(self, origin=SSH, push=None, connection_ok=True, remote_head=None):
        self.origin = origin
        self.push = push if push is not None else origin
        self.connection_ok = connection_ok
        self.remote_head = remote_head
        self.calls = []
        self.list_count = 0

    def git(self, *args, **kwargs):
        if args[:2] == ("remote", "get-url"):
            return self.push if "--push" in args else self.origin
        if args[0] == "status":
            return ""
        if args[0] == "cat-file":
            return "tag"
        if args[0] == "rev-parse":
            return HEAD
        raise AssertionError("Unexpected git query: " + repr(args))

    def run(self, args, **kwargs):
        self.calls.append(args)
        if args[:3] == ["git", "remote", "get-url"]:
            return 0, self.push if "--push" in args else self.origin
        if args == ["git", "remote"]:
            return 0, "origin\n"
        if args[:2] == ["gh", "api"]:
            endpoint = args[2] if args[2] != "--hostname" else "user"
            if endpoint == "user":
                return 0, "Heavenly-cyber\n"
            if "/releases/tags/" in endpoint:
                return 1, "HTTP 404: Not Found"
            return 0, json.dumps({"owner": {"login": "Heavenly-Cyber"}, "private": True})
        if "ls-remote" in args:
            self.list_count += 1
            if not self.connection_ok:
                return 128, "Permission denied (publickey)."
            value = self.remote_head if self.list_count == 1 else HEAD
            return 0, value + "\trefs/heads/main\n" if value else ""
        if args[:3] == ["git", "cat-file", "-e"]:
            return 1, "Unknown remote object"
        if "push" in args:
            return 0, "saved"
        if args[:2] == ["git", "archive"]:
            archive = Path(args[args.index("--output") + 1])
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("rocket_proplusion_project/README.md", "simulated source archive\n")
            return 0, ""
        if args[:2] == ["gh", "release"]:
            return 0, "created"
        raise AssertionError("Unexpected simulated command: " + repr(args))


def test_expected_repository_https_and_ssh_urls(tmp_path):
    with modules(tmp_path) as (common, publication):
        assert publication.remote_transport(SSH) == "ssh"
        assert publication.remote_transport("ssh://git@github.com/Heavenly-Cyber/rocket_proplusion_project") == "ssh"
        assert publication.remote_transport(publication.URL) == "https"
        for value in ("git@github.com:another/rocket_proplusion_project.git", SSH + "/extra",
                      "https://github.com.evil.test/Heavenly-Cyber/rocket_proplusion_project.git",
                      "https://token@github.com/Heavenly-Cyber/rocket_proplusion_project.git"):
            try:
                publication.remote_transport(value)
            except common.ProjectError:
                pass
            else:
                raise AssertionError("Unexpected origin was accepted: " + value)


def test_both_fetch_and_push_destinations_are_checked(tmp_path):
    with modules(tmp_path) as (common, publication):
        fake = Adapter()
        assert publication.checked_origin(fake)
        assert len(fake.calls) == 2
        for fake in (Adapter(push="git@github.com:another/repo.git"), Adapter(origin=SSH + "\n" + SSH)):
            try:
                publication.checked_origin(fake)
            except common.ProjectError:
                pass
            else:
                raise AssertionError("Unverified/multiple origin URLs were accepted.")


def test_transport_settings_are_scoped_and_origin_is_preserved(tmp_path):
    with modules(tmp_path) as (_, publication):
        fake = Adapter()
        prefix, transports = publication.git_transport(fake)
        assert transports == {"ssh"} and fake.origin == SSH
        assert any("BatchMode=yes" in value and "StrictHostKeyChecking=yes" in value for value in prefix)
        prefix, transports = publication.git_transport(Adapter(origin=publication.URL))
        assert transports == {"https"} and not any("sshCommand" in value for value in prefix)
        assert not list(tmp_path.iterdir())


def test_ssh_origin_publication_keeps_remote_and_saves_three_tags(tmp_path):
    with modules(tmp_path) as (_, publication):
        fake = Adapter()
        publication.publish(fake)
        assert fake.origin == SSH
        assert not any(args[:2] == ["git", "config"] or args[:3] in
                       (["git", "remote", "add"], ["git", "remote", "set-url"]) for args in fake.calls)
        push = next(args for args in fake.calls if "push" in args)
        assert "--atomic" in push and not any("force" in value for value in push)
        assert all("refs/tags/" + tag + ":refs/tags/" + tag in push for tag in publication.TAGS)
        assert len([args for args in fake.calls if args[:3] == ["gh", "release", "create"]]) == 3
        receipt = json.loads((tmp_path / "logs/setup/github-publication.json").read_text())
        assert receipt["publication_verified"] and receipt["main_commit"] == HEAD


def test_ssh_access_failure_preserves_work_before_push(tmp_path):
    with modules(tmp_path) as (common, publication):
        fake = Adapter(connection_ok=False)
        try:
            publication.publish(fake)
        except common.ProjectError as error:
            assert "ssh -T git@github.com" in str(error)
        else:
            raise AssertionError("Unverified SSH access reached publication.")
        assert not any("push" in args or args[:2] == ["gh", "release"] for args in fake.calls)
        assert fake.origin == SSH


def test_unfamiliar_remote_main_is_preserved(tmp_path):
    with modules(tmp_path) as (common, publication):
        fake = Adapter(remote_head="b" * 40)
        try:
            publication.publish(fake)
        except common.ProjectError as error:
            assert "unfamiliar/divergent" in str(error)
        else:
            raise AssertionError("An unfamiliar remote was overwritten.")
        assert not any("push" in args for args in fake.calls)
