from pathlib import Path

from gcp_rag_mcp.config import Settings


def test_by_default_it_uses_the_production_index_and_the_bge_m3_files_of_the_rag_repository():
    settings = Settings.from_env({})

    assert "/full_SEMH_bge?" in settings.database_url
    assert "connect_timeout=5" in settings.database_url  # a database that is down fails in seconds, not after the system timeout
    assert settings.model_dir.parts[-2:] == ("models", "bge-m3")
    assert settings.model_dir.is_absolute()


def test_the_environment_overrides_the_database_and_the_model_directory(tmp_path):
    settings = Settings.from_env({"RAG_DATABASE_URL": "postgresql://u:p@db:5432/other", "RAG_MODEL_DIR": str(tmp_path)})

    assert settings.database_url == "postgresql://u:p@db:5432/other"
    assert settings.model_dir == Path(tmp_path)
