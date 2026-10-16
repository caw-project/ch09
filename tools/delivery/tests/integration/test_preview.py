"""The preview deploy the workflow runs before each acceptance pass: retried once, and a
failure — even of the deploy script itself — handed to the agent, never a crash."""

from __future__ import annotations

from delivery.run.preview import deploy_preview


def deploy(tmp_path, script, **kw):
    return deploy_preview(
        tmp_path,
        evidence="build/acceptance",
        branch="feature/gh-3",
        deploy_sh=script,
        retry_wait=0,
        sleep=lambda _: None,
        log=lambda _: None,
        **kw,
    )


def test_a_deploy_that_prints_its_origin_is_up(tmp_path):
    script = tmp_path / "deploy"
    script.write_text("#!/bin/sh\necho APP_ORIGIN=https://x.example\n")
    script.chmod(0o755)

    assert (
        deploy(tmp_path, str(script))
        == "up at https://x.example — log: build/acceptance/preview-up.log"
    )


def test_a_missing_deploy_script_fails_twice_without_crashing(tmp_path):
    said = deploy(tmp_path, "scripts/no-such-deploy.sh")

    assert said == "failed twice — log: build/acceptance/preview-up.log"
    assert "no-such-deploy.sh" in (tmp_path / "build/acceptance/preview-up.log").read_text()
