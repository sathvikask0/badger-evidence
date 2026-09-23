"""End-to-end: start the MCP server over stdio and call every tool like a client would."""
import asyncio
import json
import sys
import unittest
from pathlib import Path

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:  # optional dependency
    ClientSession = None

ROOT = Path(__file__).resolve().parent.parent


async def call_all():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "badger_evidence" / "mcp_server.py")], cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            init = await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            async def call(tool, **args):
                res = await s.call_tool(tool, args)
                assert not res.isError, res.content
                return json.loads(res.content[0].text)
            out = {"instructions": init.instructions, "tools": tools,
                   "info": await call("dataset_info"),
                   "targets": await call("list_targets"),
                   "search": await call("search_measurements", target="mTOR", source="both", endpoint="IC50", limit=5),
                   "summary": await call("potency_summary", target="PARP1", endpoint="IC50"),
                   "profile": await call("compound_profile", name="olaparib")}
            first_paper = (await call("search_measurements", target="PARP1", limit=1))["results"][0]
            out["evidence"] = await call("get_evidence", record_id=first_paper["id"])
            out["chembl_evidence"] = await call("get_evidence", record_id=out["search"]["results"][0]["id"]) if out["search"]["results"][0]["source"] == "chembl" else None
            bad = await s.call_tool("search_measurements", {"target": "not-an-enzyme"})
            out["bad_is_error"] = bad.isError
            return out


@unittest.skipIf(ClientSession is None, "mcp package not installed")
class McpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = asyncio.run(call_all())

    def test_tools_and_instructions(self):
        self.assertEqual(self.out["tools"], {"dataset_info", "list_targets", "search_measurements", "get_evidence", "potency_summary", "compound_profile"})
        self.assertIn("cite", self.out["instructions"])

    def test_every_paper_result_is_cited(self):
        for r in self.out["search"]["results"] + self.out["summary"]["most_potent"]:
            c = r["citation"]
            self.assertTrue(c.get("pmcid") or c.get("chembl_activity"))

    def test_results_sorted_and_single_endpoint(self):
        vals = [r["value_nm"] for r in self.out["search"]["results"]]
        self.assertEqual(vals, sorted(vals))
        self.assertEqual({r["endpoint"] for r in self.out["search"]["results"]}, {"IC50"})

    def test_evidence_shows_source_cell(self):
        ev = self.out["evidence"]
        self.assertTrue(any(c["extracted"] for c in ev["source_row"]))
        self.assertEqual(len(ev["source_sha256"]), 64)

    def test_compound_profile_and_errors(self):
        self.assertIn("PARP1", self.out["profile"]["targets"])
        self.assertTrue(self.out["bad_is_error"])
