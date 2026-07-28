import json
from unittest.mock import patch, MagicMock
from app.repositories.project_repository import ProjectRepository
from database.database import Project as LegacyProject

@patch('database.database.SessionLocal')
def test_save_legacy_project_new(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = None

    doc_id = "test_doc"
    name = "Test Project"
    results = {
        "What is this?": {
            "best_answer": "It is a test.",
            "alternatives": [
                {"response": "Test", "score": 0.9, "summary": "t", "page_number": 1, "chunk_id": "c1", "chunk_text": "text"}
            ]
        }
    }

    result = ProjectRepository.save_legacy_project(doc_id, name, json.dumps(results))

    assert result == {"message": "Projet et questions sauvegardes avec succes"}
    assert mock_db.add.called
    assert mock_db.commit.called
    mock_db.close.assert_called_once()

@patch('database.database.SessionLocal')
def test_save_legacy_project_existing(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = LegacyProject(id="test_doc", name="Test Project")

    result = ProjectRepository.save_legacy_project("test_doc", "Test Project", "{}")

    assert result == {"message": "Deja existant"}
    mock_db.close.assert_called_once()

@patch('app.repositories.feedback_repository.open')
def test_store_legacy_feedback(mock_open):
    from app.repositories.feedback_repository import FeedbackRepository
    FeedbackRepository.store_legacy_feedback("q", "a", 1.0)
    mock_open.assert_called_once()
