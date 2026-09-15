import asyncio
import unittest
from agents.router import SemanticRouter
from agents.workflow_compiler import WorkflowCompiler
from database.db import get_db_connection


class TestRoutingAndCompilerFixes(unittest.TestCase):

    def test_leave_audit_does_not_route_to_onboarding(self):
        """Verify 'daftar cuti pending' goes to HR leave audit, not Finance onboarding."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                SemanticRouter.route_prompt("Daftar cuti pending teknisi minggu ini", tenant_id="HR")
            )
            wf_id = result.get("workflow_id")
            self.assertIsNotNone(wf_id)
            
            # Look up matched workflow in DB to verify it belongs to HR and is about Leave
            conn = get_db_connection(read_only=True)
            wf = conn.execute("SELECT id, name, tenant_id FROM workflows WHERE id = ?", [wf_id]).fetchone()
            conn.close()
            
            self.assertIsNotNone(wf, f"Workflow {wf_id} must exist in DB")
            self.assertEqual(wf[2], "HR", "Matched workflow tenant must be HR")
            self.assertIn("cuti", wf[1].lower(), "Matched workflow name must relate to leave/cuti")
        finally:
            loop.close()

    def test_stock_query_does_not_route_to_wf005_opex(self):
        """Verify stock query never routes to WF-005 (Audit Beban Listrik PLN)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                SemanticRouter.route_prompt("Berapa sisa stok kabel fiber optik di gudang Bandung?", tenant_id="INVENTORY")
            )
            # Must NOT be WF-005 (WF-005 is strictly for OPEX/Listrik PLN)
            self.assertNotEqual(result.get("workflow_id"), "WF-005")
        finally:
            loop.close()

    def test_unrelated_prompt_anti_hallucination(self):
        """Verify unrelated / chit-chat prompts are marked unrelated, not restock."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                SemanticRouter.route_prompt("Halo cuaca hari ini cerah sekali ya di luar kantor", tenant_id="ALL")
            )
            self.assertTrue(result.get("is_unrelated") or result.get("workflow_id") is None)
        finally:
            loop.close()

    def test_workflow_compiler_safe_fallback(self):
        """Verify workflow compiler fallback does not inject low stock tools blindly."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            compiled = loop.run_until_complete(
                WorkflowCompiler.compile_business_instruction(
                    name="Workflow Konsultasi Khusus",
                    instruction="Berikan analisis ringkas mengenai efisiensi operasional"
                )
            )
            tools = [s.get("tool") for s in compiled.get("steps", []) if s.get("type") == "tool"]
            # Must NOT include inventory.get_low_stock_products or calculate_reorder_quantity
            self.assertNotIn("inventory.get_low_stock_products", tools)
            self.assertNotIn("calculate_reorder_quantity", tools)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
