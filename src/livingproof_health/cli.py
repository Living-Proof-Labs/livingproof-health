# SPDX-License-Identifier: Apache-2.0
"""Minimal Health CLI command and Living Proof capability plugin entry point."""

import click


def show_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    from .version import current_version

    identity, package_version, source = current_version()
    click.echo(f"livingproof-health, version {identity}")
    click.echo(f"Package: {package_version}; identity source: {source}")
    ctx.exit()


@click.group(invoke_without_command=True)
@click.option(
    "--version",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=show_version,
    help="Show release or development identity, package version, and provenance source.",
)
@click.pass_context
def health(ctx):
    """Robot wellness and time-indexed health observation commands (bootstrap).

    This bootstrap registers the ``health`` plugin under ``livingproof capability``
    and the standalone ``livingproof-health`` command. Health snapshot, replay,
    and evaluation commands are not implemented yet and are tracked in issue #1.

    Health assumes only time is available; individual observations are optional,
    and missing data is not treated as healthy. No ROS, Foxglove, paid service,
    or specific robot telemetry field is required.

    \b
    Available commands today:
      livingproof-health --help
      livingproof-health --version
      livingproof capability health --help
      livingproof capability health --version
    """
    if ctx.resilient_parsing:
        return
    if ctx.invoked_subcommand is None:
        command = ctx.command_path or "livingproof-health"
        raise click.ClickException(
            "Health observation and snapshot commands are not implemented in this "
            "bootstrap yet (tracked in issue #1). "
            f"Run '{command} --help' for scope or '{command} --version' for build identity."
        )
