from support_agent.agent.tools import TOOLS


def test_model_cannot_pass_a_customer_id_to_any_tool():
    for tool in TOOLS:
        params = tool.tool_call_schema.model_json_schema()["properties"]

        assert "runtime" not in params, tool.name
        assert not any("customer" in name for name in params), tool.name
