from pathlib import Path

import pytest

from gcp_rag_mcp.config import Settings
from gcp_rag_mcp.preferences import save_model


def test_by_default_it_uses_the_production_index_and_the_bge_m3_files_of_the_rag_repository(tmp_path):
    settings = Settings.from_env({"RAG_MCP_HOME": str(tmp_path)})

    assert settings.model.key == "bge-m3"
    assert "/courses_bge?" in settings.database_url
    assert "connect_timeout=5" in settings.database_url  # a database that is down fails in seconds, not after the system timeout
    assert settings.model_dir.parts[-2:] == ("models", "bge-m3")
    assert settings.model_dir.is_absolute()


def test_the_environment_overrides_the_database_and_the_model_directory(tmp_path):
    settings = Settings.from_env(
        {"RAG_MCP_HOME": str(tmp_path), "RAG_DATABASE_URL": "postgresql://u:p@db:5432/other", "RAG_MODEL_DIR": str(tmp_path)}
    )

    assert settings.database_url == "postgresql://u:p@db:5432/other"
    assert settings.model_dir == Path(tmp_path)


def test_the_model_variable_picks_the_model_its_database_and_its_files_together(tmp_path):
    settings = Settings.from_env({"RAG_MCP_HOME": str(tmp_path), "RAG_MODEL": "e5-small"})

    assert settings.model.key == "e5-small"
    assert "/courses_e5?" in settings.database_url and "connect_timeout=5" in settings.database_url
    assert settings.model_dir.parts[-2:] == ("models", "multilingual-e5-small")


def test_the_model_chosen_with_setup_or_switch_is_used_when_the_variable_is_not_set(tmp_path):
    save_model("e5-small", {"RAG_MCP_HOME": str(tmp_path)})

    assert Settings.from_env({"RAG_MCP_HOME": str(tmp_path)}).model.key == "e5-small"
    assert Settings.from_env({"RAG_MCP_HOME": str(tmp_path), "RAG_MODEL": "bge-m3"}).model.key == "bge-m3"  # the variable wins


def test_an_unknown_model_fails_at_start_up_listing_the_valid_names(tmp_path):
    with pytest.raises(ValueError, match="bge-m3, e5-small"):
        Settings.from_env({"RAG_MCP_HOME": str(tmp_path), "RAG_MODEL": "gpt"})
