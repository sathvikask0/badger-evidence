# Badger Evidence MCP server

Lets Claude (or any MCP client) query the dataset with citations.

## Tools

| tool | what it does |
|---|---|
| `dataset_info` | contents, licences and known limits |
| `list_targets` | the ~55 enzymes, why each matters for ageing, value counts |
| `search_measurements` | potency values for one enzyme, most potent first, each with a citation |
| `get_evidence` | full provenance for one value: source table row, caption, footnotes, methods, checks, structure |
| `potency_summary` | median/percentiles and the 10 most potent compounds for an enzyme + endpoint |
| `compound_profile` | everything known about a named compound across enzymes (papers + ChEMBL) |

## Use it in Claude Desktop

1. Install uv: `brew install uv`
2. Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "badger-evidence": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["run", "/Users/YOU/Desktop/badger-evidence/badger_evidence/mcp_server.py"]
    }
  }
}
```

3. Restart Claude Desktop and ask, for example:
   *"Using badger-evidence, what are the most potent mTOR inhibitors reported in open-access papers? Show the source table row for the top one and compare it with ChEMBL."*

## Inspect or test

```sh
npx @modelcontextprotocol/inspector uv run badger_evidence/mcp_server.py   # interactive (pinned to mcp 1.x)
python3 -m unittest tests.test_mcp_server -v                                # needs: pip install mcp
```
