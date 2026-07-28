"""Residence context: proposed application date and travel records (Domain §4.3).

M3A builds the versioned input layer only — the date and travel aggregates, their
immutable versions, and validation. No windows, absence totals, or assessments are
computed here; those are the M3B deterministic rules, which consume these inputs.
"""
