# SPDX-License-Identifier: Apache-2.0
"""Verify plugin discovery metadata, minimal dependencies, and CLI responses."""

from importlib.metadata import distribution

import click
from click.testing import CliRunner

from livingproof_health.cli import health

DISALLOWED_DEPENDENCY_MARKERS = ("livingproof", "ros", "rclpy", "foxglove", "boto3", "google-cloud")


def test_installed_plugin_metadata():
    package = distribution("livingproof-health")
    capability_entries = [
        entry for entry in package.entry_points if entry.group == "livingproof.capability.commands"
    ]
    assert len(capability_entries) == 1
    assert capability_entries[0].name == "health"
    loaded = capability_entries[0].load()
    assert loaded is health
    assert isinstance(loaded, click.Command)

    script_entries = [entry for entry in package.entry_points if entry.group == "console_scripts"]
    assert [entry.name for entry in script_entries] == ["livingproof-health"]
    assert script_entries[0].load() is health


def test_minimal_dependency_boundary():
    package = distribution("livingproof-health")
    requirements = [
        requirement.split(";")[0].strip().split()[0].split("==")[0].lower()
        for requirement in (package.requires or [])
    ]
    assert "livingproof" not in requirements
    for req in requirements:
        if req == "livingproof-common":
            continue
        assert not any(marker in req for marker in DISALLOWED_DEPENDENCY_MARKERS), req


def test_help_is_useful():
    result = CliRunner().invoke(health, ["--help"], prog_name="livingproof-health")
    assert result.exit_code == 0
    assert "Usage: livingproof-health" in result.output
    assert "issue #1" in result.output
    assert "--version" in result.output
    assert "ROS" in result.output and "Foxglove" in result.output


def test_no_command_response_is_clear():
    result = CliRunner().invoke(health, [], prog_name="livingproof capability health")
    assert result.exit_code == 1
    assert result.exception is not None
    assert "Choose a command" in result.output
    assert "livingproof capability health --help" in result.output
    assert "Traceback" not in result.output


def test_unknown_subcommand_fails_cleanly():
    result = CliRunner().invoke(health, ["snapshot"], prog_name="livingproof-health")
    assert result.exit_code == 2
    assert "No such command 'snapshot'" in result.output
