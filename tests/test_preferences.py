from gcp_rag_mcp.preferences import load_model, save_model


def test_nothing_is_saved_until_a_model_is_chosen(tmp_path):
    assert load_model({"RAG_MCP_HOME": str(tmp_path)}) is None


def test_the_chosen_model_is_remembered(tmp_path):
    env = {"RAG_MCP_HOME": str(tmp_path / "new-folder")}  # the folder is created on the first save

    save_model("e5-small", env)

    assert load_model(env) == "e5-small"


def test_a_damaged_preferences_file_is_ignored_instead_of_breaking_the_server(tmp_path):
    (tmp_path / "preferences.json").write_text("{not json", encoding="utf-8")

    assert load_model({"RAG_MCP_HOME": str(tmp_path)}) is None
