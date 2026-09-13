"""Exceptions shared across modules."""


class TeraseringError(Exception):
    """Base class for every terasering error."""


class ProblemLoadError(TeraseringError):
    """A problem definition on disk is invalid. Messages target the admin."""


class ToolchainError(TeraseringError):
    """The compiler is missing or unusable."""


class SandboxError(TeraseringError):
    """Execution failed because of the environment, not the submitted code."""
