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
@click.option(
    "--limits",
    "limits_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSON budget overrides (<=4 KiB); each limit has a documented hard ceiling.",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Atomically replace a JSON file only after complete validation; default stdout.",
)
def replay(recording, topic, limits_path, output):
    """Convert MCAP to portable health JSON on stdout, preserving every pose sample.

    Example: livingproof-health replay trial.mcap > health.json
    MCAP log_time is the clock. JSON timestamps are decimal strings (not numbers).
    Input must use the simulation recorder's
    JSON PoseInFrame schema; selecting it does not establish hardware provenance.
    Input/output resource limits apply; see docs/bounded-replay.md for defaults and overrides.
    No partial JSON is emitted on validation/budget failure. For atomic files, use --output.
    Next: livingproof-health seek health.json --time-ns 20000000
    """
    from mcap.exceptions import McapError
    from .recording import read_mcap
    from .bounds import Limits, replay_json
    import os
    import shutil
    import tempfile
    import sys

    try:
        limits = Limits.from_file(limits_path) if limits_path else Limits()
        result = read_mcap(recording, topic=topic, limits=limits)
        with replay_json(result, limits) as stream:
            if output is None:
                shutil.copyfileobj(stream, sys.stdout.buffer, length=65536)
            else:
                pending = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=output.parent, prefix=".health-", delete=False
                    ) as destination:
                        pending = Path(destination.name)
                        shutil.copyfileobj(stream, destination, length=65536)
                    os.replace(pending, output)
                finally:
                    if pending is not None:
                        pending.unlink(missing_ok=True)
    except (ValueError, OSError, McapError, EOFError, StructError, RecursionError) as exc:
        raise click.ClickException(
            f"Cannot read pose recording: {str(exc) or 'empty or truncated MCAP'}. See 'replay --help'."
        ) from exc


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

    from .snapshots import snapshot_to_wire

    found = read_replay(recording).seek(time_ns)
    wire = snapshot_to_wire(found) if found is not None else None
    click.echo(json.dumps(wire, sort_keys=True, allow_nan=False))


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
    from .assessment import assess_base_height, assessment_to_json

    try:
        result = assess_base_height(read_replay(recording), minimum_m=minimum_m, frame_id=frame_id)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc
    click.echo(assessment_to_json(result))
    raise click.exceptions.Exit(
        {"PASS": 0, "FAIL": 1, "INSUFFICIENT_EVIDENCE": 2}[result["status"]]
    )
