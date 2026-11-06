"""Timekeeping write operations and business rules.

Services are plain functions that take explicit arguments, run inside
transactions where needed, and raise common.exceptions.ApplicationError on
rule violations. Views call services; services never import from api/.
"""
