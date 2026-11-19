# Contribute

Read and apply
[collaboration-guidelines v9.7.3](https://github.com/Living-Proof-Labs/collaboration-guidelines/blob/v9.7.3/AGENTS.md)
and its linked procedures at that tag, together with this repository's
[working agreement](AGENTS.md).

Use a focused draft pull request and verify changes before review:

```sh
task setup
task verify
```

To include the isolated wheel and `livingproof` host CLI installation check:

```sh
LIVINGPROOF_NETWORK=1 task verify
```

On a host with Docker and Compose, run:

```sh
task dev:verify
```

This Docker command enables the online installed-host integration test. CI uses
the documented Ubuntu fallback and does not exercise Docker. See the README
for the image-publication (#4) and generated-manual (#5) follow-ups.

Keep Health observations separate from scenario pass/fail criteria, preserve
missing-data semantics (missing data is not healthy data), and do not introduce
ROS, Foxglove, or paid-service requirements into the core package or plugin.
