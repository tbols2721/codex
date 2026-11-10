#!/usr/bin/env python3
"""Exercise update history, conflicts, receipt gates, and rollback in temp repos."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import update


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="codex-statusline-git-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "source"
        self.origin = self.root / "origin.git"
        self.upstream = self.root / "upstream.git"
        update.run("git", "init", "--quiet", "--bare", self.origin)
        update.run("git", "init", "--quiet", "--bare", self.upstream)
        update.run("git", "init", "--quiet", "-b", "upstream", self.repo)
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.write("codex-rs/Cargo.toml", '[workspace.package]\nversion = "1.0.0"\n')
        self.write("codex-rs/Cargo.lock", "initial lock\n")
        self.write("feature.txt", "upstream original\n")
        self.save("Release one")
        self.git("tag", "rust-v1.0.0")
        self.base_commit = update.commit(self.repo)
        self.git("switch", "--quiet", "-c", update.BRANCH)
        self.write("feature.txt", "custom rows\n")
        update.write_json(self.repo / update.METADATA, {
            "schema": 1, "repository": "openai/codex", "tag": "rust-v1.0.0",
            "version": "1.0.0", "commit": self.base_commit,
        })
        self.save("Custom feature")
        self.original = update.commit(self.repo)
        self.git("remote", "add", "origin", self.origin)
        self.git("remote", "add", "upstream", self.upstream)
        self.git("push", "--quiet", "origin", update.BRANCH, "refs/tags/rust-v1.0.0")
        self.git("push", "--quiet", "upstream", "upstream", "refs/tags/rust-v1.0.0")
        self.args = SimpleNamespace(
            source=self.repo, updates=self.root / "updates", state=self.root / "state",
            packages=self.root / "packages", target=self.root / "target", toolchain="test",
            profile="test", tag="rust-v1.1.0",
        )
        self.args.state.mkdir()

    def git(self, *arguments, **kwargs):
        return update.git(self.repo, *arguments, **kwargs)

    def write(self, relative, data):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)

    def save(self, message):
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", message)

    def release(self, conflict=False, annotated=False):
        self.git("switch", "--quiet", "upstream")
        self.write("codex-rs/Cargo.toml", '[workspace.package]\nversion = "1.1.0"\n')
        if conflict:
            self.write("feature.txt", "new upstream implementation\n")
        else:
            self.write("new-upstream.txt", "new release\n")
        self.save("Release two")
        if annotated:
            self.git("tag", "-a", self.args.tag, "-m", "Annotated upstream release")
        else:
            self.git("tag", self.args.tag)
        self.git("push", "--quiet", "upstream", f"refs/tags/{self.args.tag}")
        self.git("switch", "--quiet", update.BRANCH)

    def stage(self):
        real_run = update.run

        def run(*arguments, **kwargs):
            if arguments[0] == "cargo":
                return None  # This test exercises Git, not Cargo itself.
            return real_run(*arguments, **kwargs)

        with patch.object(update, "stable_release", return_value={}), patch.object(update, "run", side_effect=run):
            update.stage(self.args)
        self.args.candidate = self.args.updates / "1.1.0"

    def package(self, label):
        directory = self.args.packages / label
        (directory / "bin").mkdir(parents=True)
        binary = directory / "bin/codex"
        binary.write_text(label)
        binary.chmod(0o755)
        (directory / "bin/codex-code-mode-host").write_text("matching helper")
        (directory / "bin/codex-code-mode-host").chmod(0o755)
        return directory, update.fingerprint(binary)

    def receipt(self):
        package, digest = self.package("new")
        update.write_json(update.receipt_path(self.args, self.args.candidate), {
            "commit": update.commit(self.args.candidate), "tag": self.args.tag,
            "package": str(package), "binary_sha256": digest,
            "package_files": update.package_files(package),
        })
        return package, digest

    def test_staging_and_promotion_keep_feature_and_old_history(self):
        self.release()
        self.stage()
        self.assertEqual(update.commit(self.repo), self.original)
        self.assertEqual((self.args.candidate / "feature.txt").read_text(), "custom rows\n")
        self.assertEqual(update.metadata(self.args.candidate)["version"], "1.1.0")
        package, digest = self.receipt()
        old_package, old_digest = self.package("old")
        update.write_json(self.args.state / "installation.json", {
            "current": str(old_package), "current_sha256": old_digest,
            "current_files": update.package_files(old_package),
        })
        update.point_link(self.repo / "bin/codex-statusline", old_package / "bin/codex")
        self.git("config", "core.excludesFile", self.root / "test-ignore")
        (self.root / "test-ignore").write_text("/bin/\n")
        update.promote(self.args)
        new_head = update.commit(self.repo)
        self.assertEqual(new_head, update.commit(self.args.candidate))
        self.assertEqual(self.git("rev-parse", "origin/custom-main", capture=True), new_head)
        remote_tag = update.run("git", "--git-dir", self.origin, "rev-parse", f"{self.args.tag}^{{commit}}", capture=True)
        self.assertEqual(remote_tag, self.git("rev-parse", f"{self.args.tag}^{{commit}}", capture=True))
        self.git("merge-base", "--is-ancestor", self.original, "HEAD")
        tags = self.git("tag", "--list", "statusline-before-*", capture=True).splitlines()
        self.assertEqual(len(tags), 1)
        self.assertEqual(self.git("rev-parse", f"{tags[0]}^{{commit}}", capture=True), self.original)
        self.assertEqual((self.repo / "bin/codex-statusline").resolve(), package / "bin/codex")
        update.rollback(self.args)
        self.assertEqual((self.repo / "bin/codex-statusline").resolve(), old_package / "bin/codex")
        self.assertEqual(update.commit(self.repo), new_head)

    def test_conflict_leaves_main_and_existing_binary_untouched(self):
        self.release(conflict=True)
        with self.assertRaises(update.Stop):
            self.stage()
        self.assertEqual(update.commit(self.repo), self.original)
        self.assertIn("UU feature.txt", update.git(self.args.updates / "1.1.0", "status", "--porcelain", capture=True))
        self.assertFalse((self.repo / "bin/codex-statusline").exists())

    def test_annotated_release_can_be_staged(self):
        self.release(annotated=True)
        self.stage()
        self.assertEqual(update.metadata(self.args.candidate)["version"], "1.1.0")
        self.assertEqual(update.commit(self.repo), self.original)

    def test_changed_binary_cannot_be_promoted(self):
        self.release()
        self.stage()
        package, _ = self.receipt()
        (package / "bin/codex").write_text("changed after verification")
        with self.assertRaises(update.Stop):
            update.promote(self.args)
        self.assertEqual(update.commit(self.repo), self.original)

    def test_first_update_refuses_to_discard_unrecorded_binary(self):
        self.release()
        self.stage()
        self.receipt()
        self.git("config", "core.excludesFile", self.root / "test-ignore")
        (self.root / "test-ignore").write_text("/bin/\n")
        (self.repo / "bin").mkdir()
        (self.repo / "bin/codex-statusline").write_text("unrecorded old build")
        (self.repo / "bin/codex-code-mode-host").write_text("old helper")
        with self.assertRaises(update.Stop):
            update.promote(self.args)
        self.assertEqual(update.commit(self.repo), self.original)
        self.assertEqual((self.repo / "bin/codex-statusline").read_text(), "unrecorded old build")

    def test_first_adoption_retains_a_rollback_copy(self):
        self.args.candidate = self.repo
        self.args.tag = "rust-v1.0.0"
        package, _ = self.receipt()
        self.git("config", "core.excludesFile", self.root / "test-ignore")
        (self.root / "test-ignore").write_text("/bin/\n")
        (self.repo / "bin").mkdir()
        (self.repo / "bin/codex-statusline").write_bytes((package / "bin/codex").read_bytes())
        (self.repo / "bin/codex-code-mode-host").write_bytes((package / "bin/codex-code-mode-host").read_bytes())
        update.promote(self.args)
        update.rollback(self.args)
        self.assertEqual((self.repo / "bin/codex-statusline").resolve(), package / "bin/codex")

    def test_changed_helper_or_mode_cannot_be_promoted(self):
        self.release()
        self.stage()
        package, _ = self.receipt()
        helper = package / "bin/codex-code-mode-host"
        helper.write_text("different helper")
        with self.assertRaises(update.Stop):
            update.promote(self.args)
        helper.write_text("matching helper")
        helper.chmod(0o644)
        with self.assertRaises(update.Stop):
            update.promote(self.args)
        self.assertEqual(update.commit(self.repo), self.original)

    def test_first_different_build_archives_existing_trial(self):
        self.release()
        self.stage()
        self.receipt()
        old_package, old_digest = self.package("old")
        self.git("config", "core.excludesFile", self.root / "test-ignore")
        (self.root / "test-ignore").write_text("/bin/\n")
        (self.repo / "bin").mkdir()
        old_launcher = self.repo / "bin/codex-statusline"
        old_launcher.write_bytes((old_package / "bin/codex").read_bytes())
        old_launcher.chmod(0o755)
        (self.repo / "bin/codex-code-mode-host").symlink_to(old_package / "bin/codex-code-mode-host")
        with patch.object(update, "binary_version", return_value="codex-cli 1.0.0"):
            update.promote(self.args)
        state = json.loads((self.args.state / "installation.json").read_text())
        self.assertEqual(state["previous_sha256"], old_digest)
        self.assertNotEqual(state["previous"], str(old_package))
        preserved_helper = Path(state["previous"]) / "bin/codex-code-mode-host"
        self.assertFalse(preserved_helper.is_symlink())
        update.rollback(self.args)
        self.assertEqual(update.fingerprint(old_launcher), old_digest)

    def test_failed_state_write_restores_old_selection(self):
        old_package, old_digest = self.package("old")
        new_package, new_digest = self.package("new")
        old = {"current": str(old_package), "current_sha256": old_digest}
        new = {"current": str(new_package), "current_sha256": new_digest}
        state_file = self.args.state / "installation.json"
        update.write_json(state_file, old)
        update.point_link(self.repo / "bin/codex-statusline", old_package / "bin/codex")
        real_write = update.write_json

        def fail_once(path, data):
            if path == state_file and data == new:
                raise OSError("injected state write failure")
            return real_write(path, data)

        with patch.object(update, "write_json", side_effect=fail_once), self.assertRaises(OSError):
            update.switch_package(self.args, old, new, old_package / "bin/codex")
        self.assertEqual(json.loads(state_file.read_text()), old)
        self.assertEqual((self.repo / "bin/codex-statusline").resolve(), old_package / "bin/codex")
        self.assertFalse((self.args.state / "pending-switch.json").exists())

    def test_interrupted_switch_recovers_matching_state(self):
        old_package, _ = self.package("old")
        new_package, _ = self.package("new")
        old = {"current": str(old_package)}
        new = {"current": str(new_package)}
        update.point_link(self.repo / "bin/codex-statusline", new_package / "bin/codex")
        update.write_json(self.args.state / "installation.json", old)
        update.write_json(self.args.state / "pending-switch.json", {
            "old_actual": str(old_package / "bin/codex"),
            "old_restore": str(old_package / "bin/codex"),
            "new_target": str(new_package / "bin/codex"), "old_state": old, "new_state": new,
        })
        update.recover_switch(self.args)
        self.assertEqual(json.loads((self.args.state / "installation.json").read_text()), new)
        self.assertFalse((self.args.state / "pending-switch.json").exists())

    def test_failed_link_switch_keeps_old_state(self):
        old_package, old_digest = self.package("old")
        new_package, new_digest = self.package("new")
        old = {"current": str(old_package), "current_sha256": old_digest}
        new = {"current": str(new_package), "current_sha256": new_digest}
        state_file = self.args.state / "installation.json"
        update.write_json(state_file, old)
        update.point_link(self.repo / "bin/codex-statusline", old_package / "bin/codex")
        real_link = update.point_link

        def fail_new(path, target):
            if target == new_package / "bin/codex":
                raise OSError("injected link failure")
            return real_link(path, target)

        with patch.object(update, "point_link", side_effect=fail_new), self.assertRaises(OSError):
            update.switch_package(self.args, old, new, old_package / "bin/codex")
        self.assertEqual(json.loads(state_file.read_text()), old)
        self.assertEqual((self.repo / "bin/codex-statusline").resolve(), old_package / "bin/codex")

    def test_interrupted_legacy_archive_recovers_before_switch(self):
        old_package, _ = self.package("old")
        new_package, _ = self.package("new")
        old = {"current": str(old_package)}
        new = {"current": str(new_package)}
        launcher = self.repo / "bin/codex-statusline"
        launcher.parent.mkdir()
        launcher.write_bytes((old_package / "bin/codex").read_bytes())
        update.write_json(self.args.state / "pending-switch.json", {
            "old_actual": str(launcher), "old_restore": str(old_package / "bin/codex"),
            "new_target": str(new_package / "bin/codex"), "old_state": old, "new_state": new,
        })
        update.recover_switch(self.args)
        self.assertEqual(launcher.resolve(), old_package / "bin/codex")
        self.assertEqual(json.loads((self.args.state / "installation.json").read_text()), old)

    def test_changed_commit_cannot_reuse_receipt(self):
        self.release()
        self.stage()
        self.receipt()
        (self.args.candidate / "later.txt").write_text("new code\n")
        update.git(self.args.candidate, "add", ".")
        update.git(self.args.candidate, "commit", "--quiet", "-m", "Later change")
        with self.assertRaises(FileNotFoundError):
            update.promote(self.args)
        self.assertEqual(update.commit(self.repo), self.original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
