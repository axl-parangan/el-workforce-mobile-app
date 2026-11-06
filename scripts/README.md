# scripts

Repository-level helper scripts (seeding, release tasks, one-off maintenance).

Prefer adding a `Makefile` target that calls a script here over documenting
long command lines. Scripts must not contain secrets; read them from the
environment.
