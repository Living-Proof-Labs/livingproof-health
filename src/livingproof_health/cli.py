# SPDX-License-Identifier: Apache-2.0
"""Minimal Health CLI command and Living Proof capability plugin entry point."""

from pathlib import Path
from struct import error as StructError

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
    """Robot wellness and time-indexed observations (first slice, issue #1).

    Only time is required. Missing observations are not healthy data.
    No ROS, Foxglove, paid service, or specific robot morphology is required.
    Convert a recording with `replay`, inspect it with `seek`, and apply an
    explicit scenario expectation with `assess`. See each command's --help.
    """
    if not ctx.resilient_parsing and ctx.invoked_subcommand is None:
        raise click.ClickException(
            f"Choose a command. Run '{ctx.command_path} --help' for examples."
        )


def read_replay(path):
    from .snapshots import Replay

    try:
        return Replay.from_json(path.read_text())
    except (ValueError, OSError) as exc:
        raise click.ClickException(f"{exc}. Expected health JSON; see 'replay --help'.") from exc


@health.command()
@click.argument("recording", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--topic", default="/base_pose", show_default=True, help="JSON PoseInFrame channel (metres)."
)
def replay(recording, topic):
    """Convert MCAP to portable health JSON on stdout, preserving every pose sample.

    Example: livingproof-health replay trial.mcap > health.json
    MCAP log_time is the clock. Input must use the simulation recorder's
    JSON PoseInFrame schema; selecting it does not establish hardware provenance.
    Next: livingproof-health seek health.json --time-ns 20000000
    """
    from mcap.exceptions import McapError
    from .recording import read_mcap

    try:
        result = read_mcap(recording, topic=topic)
    except (ValueError, OSError, McapError, EOFError, StructError) as exc:
        raise click.ClickException(
            f"Cannot read pose recording: {str(exc) or 'empty or truncated MCAP'}. See 'replay --help'."
        ) from exc
    click.echo(result.to_json(), nl=False)


@health.command()
@click.argument("recording", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--time-ns",
    required=True,
    type=click.IntRange(min=0),
    help="Nanoseconds on the recording clock.",
)
def seek(recording, time_ns):
    """Print the first snapshot at or after TIME_NS (null past the end).

    Example: livingproof-health seek health.json --time-ns 20000000
    No interpolation or carried-forward observations. Seek is not a trial verdict.
    """
    import json

    click.echo(json.dumps(read_replay(recording).seek(time_ns), sort_keys=True, allow_nan=False))


@health.command()
@click.argument("recording", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--minimum-m", required=True, type=float, help="Scenario's minimum base height in metres."
)
@click.option(
    "--frame-id", required=True, help="Scenario's expected coordinate frame; no frame inference."
)
def assess(recording, minimum_m, frame_id):
    """Assess ALL recorded samples against an explicit base-height expectation.

    Example: livingproof-health assess health.json --minimum-m 0.5 --frame-id world
    Equality passes; missing evidence cannot pass. Exits: 0 PASS, 1 FAIL,
    2 INSUFFICIENT_EVIDENCE. Invalid input also exits nonzero. Results cover recorded samples only;
    full simulation-step / whole-trial parity is not established.
    """
    import json
    from .assessment import assess_base_height

    try:
        result = assess_base_height(read_replay(recording), minimum_m=minimum_m, frame_id=frame_id)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc
    click.echo(json.dumps(result, sort_keys=True, allow_nan=False))
    raise click.exceptions.Exit(
        {"PASS": 0, "FAIL": 1, "INSUFFICIENT_EVIDENCE": 2}[result["status"]]
    )
