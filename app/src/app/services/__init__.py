"""Business operations, as plain functions taking a Session.

Extracted from web/app.py route bodies (refactor-plan.md §4.2) so the same
logic is callable from a future CLI command, not only from an HTTP handler.
Must not import from app.web or app.pipeline.runner-equivalent modules — see
the dependency-direction rule in refactor-plan.md §7.2.
"""
