# SPDX-License-Identifier: Apache-2.0
"""Record this consumer's build provenance using the pinned common library."""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from livingproof_common.versioning import Consumer, record_build


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        root = Path(self.root)
        consumer = Consumer(
            "livingproof-health",
            root / "src/livingproof_health",
            (
                "https://github.com/living-proof-labs/livingproof-health",
                "https://github.com/living-proof-labs/livingproof-health.git",
                "git@github.com:living-proof-labs/livingproof-health.git",
            ),
        )
        build_data.setdefault("artifacts", []).append(
            record_build(root, self.metadata.version, consumer)
        )
