# Tools

- Run every gate with `scripts/ci_local.sh`; one stage with `--only <stage>`.
- If `rtk` is installed, shell output is compressed. Read exact file bytes with `rtk proxy cat <file>` before editing.
- Serena (code navigation) is optional: `uv tool install serena-agent`, then it starts from `.mcp.json`.
