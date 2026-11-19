# Agent instructions

<!-- renovate: guidelines -->
[collaboration-guidelines v9.7.3](https://github.com/Living-Proof-Labs/collaboration-guidelines/blob/v9.7.3/AGENTS.md)
applies, with its procedures, to every change in this repository.
Resolved adoption commit: `6b3a47cde924e70b9dfbaa3cbda2e9fbd55aebd5`.

Local additions:
- Health core assumes only time is available; individual observations are
  optional and missing data is not healthy data.
- Keep observations separate from scenario-specific pass/fail criteria and
  never claim robot safety certification or universal health thresholds.
- Keep the package and CLI plugin usable without ROS, Foxglove, or paid
  services; do not require any particular robot or telemetry field.
- Original repository content is Apache-2.0.
- Use `task setup` and `task verify` inside the prepared Python 3.12
  environment or development container, or `task dev:verify` on a Docker host.
- Substantive changes stay in a draft PR until independent review.
- Do not enable new registry/security permissions, repository settings, or
  deployment changes without explicit authorization.
