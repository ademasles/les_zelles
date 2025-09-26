# main.py
"""Main application module for the text analysis service.
This module sets up the FastAPI application, defines endpoints for file upload, text extraction, cleaning, chunking, summarization, and querying.
It integrates various components such as extraction, cleaning, chunking, summarization, and indexing.
It also provides endpoints for saving projects and retrieving summaries.
"""
# SPDX-FileCopyrightText: 2025 Anton Demasles <

#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import subprocess
import json
import os
from io import BytesIO
from pydantic import BaseModel
import fitz  # PyMuPDF
from docx import Document

# preprocessing 
from preprocessing.extraction import extract_text_from_file
from preprocessing.cleaning import clean_pages
from preprocessing.chunking import chunk_text
from preprocessing.loading import load_queries
# NLP modules
from nlp.qa import chat_llm, answer_queries
from nlp.summarization import summarize_cctp, summarize_global
# database
from database.database import SessionLocal, Project, Query, Answer
# utils
from utils.highlight import highlight_chunk


#-----------------------------------------------------------------------------------------------
# INITIALISATION
#-----------------------------------------------------------------------------------------------
app = FastAPI() 

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À limiter en prod
    allow_methods=["*"],
    allow_headers=["*"],
)



# Stockage mémoire temporaire
documents = {}
query_results_store = {}

# Seuil pour déclencher l'entraînement du modèle
TRAIN_THRESHOLD = 100  # Nombre minimum de feedbacks requis pour l'entraînement
FEEDBACK_FILE = "feedback_dataset.jsonl" # Fichier de feedbacks
#-----------------------------------------------------------------------------------------------
# ROUTES
#-----------------------------------------------------------------------------------------------
@app.post("/upload/")
async def upload_file(file: UploadFile = File(...), doc_id: str = Form(...)):
    """
    Upload a file and process it to extract, clean, chunk, summarize, and index the text.
    :param file: The file to upload.
    :param doc_id: Unique identifier for the document.
    :return: A message indicating the processing status.
    """
    if doc_id in documents:
        raise HTTPException(status_code=400, detail="Document ID already exists")

    try:
        # Lire le contenu du fichier
        content = await file.read()

        # Sauvegarde du fichier original
        folder = f"data/{doc_id}"
        os.makedirs(folder, exist_ok=True)
        with open(f"{folder}/original.pdf", "wb") as f:
            f.write(content)

        # 1. Extraction depuis les bytes
        pages = await extract_text_from_file(content, file.filename)  # tu dois adapter cette fonction
        print("Extraction OK")

        # 2. Segmentation + nettoyage
        chunks = chunk_text(pages)
        print("Segmentation OK")

        cleaned_pages = clean_pages(chunks)
        print("Nettoyage OK")

        # 3. Résumé
        summaries = summarize_cctp(chunks)
        print("Résumé des chunks OK")

        # 4. Indexation
        documents[doc_id] = summaries

        return {"message": "Document traité", "doc_id": doc_id, "segments_count": len(summaries)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur traitement document : {e}")

@app.post("/query/")
async def query(doc_id: str = Form(...), question: str = Form(...)):
    """
    Query a specific document with a question and return the answer.
    :param doc_id: Unique identifier for the document.
    :param question: The question to ask about the document.
    :return: The answer to the question.
    """
    if doc_id not in documents:
        return {"error": "Document non trouvé"}
    try:
        result = answer_queries({question: question}, documents[doc_id])
        results = list(result.values())[0]  # Récupère la seule entrée formatée
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    
    return jsonable_encoder(results)


@app.post("/queries/")
async def run_queries(doc_id: str = Form(...)):
    """
    Run predefined queries on a specific document and return the results.
    :param doc_id: Unique identifier for the document.
    :return: The results of the queries.
    """
    if doc_id not in documents:
        raise HTTPException(status_code=404, detail="Document non trouvé")

    try:
        questions = load_queries()
        results = answer_queries(questions, documents[doc_id])
        query_results_store[doc_id] = results # Stocker les résultats pour le projet
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    return jsonable_encoder(results)



@app.get("/summary/")
async def summary(doc_id: str):
    """
    Get the summary of a specific document.
    :param doc_id: Unique identifier for the document.
    :return: The summary of the document.
    """
    if doc_id not in documents:
        return {"error": "Document non trouvé"}
    all_summaries = documents[doc_id]   
    summary = summarize_global(all_summaries, model="mistral")
    return {"summary": summary}


from fastapi import Request

@app.post("/save/")
async def save_project(request: Request):
    """
    Save the project with its queries and answers to the database.
    :param request: The request containing the project data.
    :return: A message indicating the project has been saved.
    """
    form_data = await request.form()
    doc_id = form_data.get("doc_id")
    name = form_data.get("name")
    results_json = form_data.get("results")  # JSON string contenant les questions/réponses

    if not all([doc_id, name, results_json]):
        return {"error": "doc_id, name et results sont nécessaires"}

    import json
    results = json.loads(results_json)

    db = SessionLocal()
    project = db.query(Project).filter(Project.id == doc_id).first()

    if not project:
        summary = summarize_global(documents.get(doc_id, []))
        new_proj = Project(id=doc_id, name=name, summary=summary)
        db.add(new_proj)
        db.commit()
    else:
        return {"message": "Déjà existant"}

    # Maintenant enregistrer les questions + réponses
    for question, result in results.items():
        new_query = Query(
            project_id=doc_id,
            question=question,
            best_answer=result.get("best_answer")
        )
        db.add(new_query)
        db.commit()
        db.refresh(new_query)

        for alt in result.get("alternatives", []):
            answer = Answer(
                query_id=new_query.id,
                response=alt.get("response"),
                score=alt.get("score"),
                summary=alt.get("summary"),
                page_number=alt.get("page_number"),
                chunk_id=alt.get("chunk_id"),
                excerpt=alt.get("chunk_text")
            )
            db.add(answer)
        db.commit()

    return {"message": "Projet et questions sauvegardés avec succès"}


        
@app.get("/projects/")
def get_projects():
    """
    Retrieve all saved projects.
    :return: A list of all projects.
    """
    db = SessionLocal()
    projects = db.query(Project).all()
    return [p.as_dict() for p in projects] or []

class FeedbackEntry(BaseModel):
    """
    Model for feedback entries.
    Contains the question, response, and user score.
    """
    question: str
    response: str
    score: float

@app.post("/feedback/")
def store_feedback(entry: FeedbackEntry):
    """
    Store user feedback for a specific question and response.
    :param entry: The feedback entry containing question, response, and score.
    :return: A message indicating the feedback has been saved.
    """
    with open("feedback_dataset.jsonl", "a", encoding="utf-8") as f:
        json.dump(entry.dict(), f)
        f.write("\n")
    return {"status": "ok"}


@app.get("/project_queries/{doc_id}")
def get_project_queries(doc_id: str):
    """
    Retrieve all questions and answers for a given project.
    :param doc_id: Unique identifier for the project.
    :return: Dictionary of query_label: query_result
    """
    db = SessionLocal()
    project = db.query(Project).filter(Project.id == doc_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    queries = db.query(Query).filter(Query.project_id == doc_id).all()
    output = {}

    for query in queries:
        answers = db.query(Answer).filter(Answer.query_id == query.id).all()
        alternatives = []
        for ans in answers:
            alternatives.append({
                "response": ans.response,
                "score": ans.score,
                "summary": ans.summary,
                "page_number": ans.page_number,
                "chunk_id": ans.chunk_id,
                "chunk_text": ans.excerpt
            })

        output[query.question] = {
            "question": query.question,
            "best_answer": query.best_answer,
            "alternatives": alternatives
        }

    return output


from fastapi import Request

@app.post("/project_queries/add")
async def add_query_to_project(request: Request):
    """
    Add a user-defined question and its AI-generated answers to a project.
    :param request: The request containing the project ID, question, and result JSON.
    :return: A message indicating the question has been added to the project.
    """
    form_data = await request.form()
    doc_id = form_data.get("doc_id")
    question = form_data.get("question")
    result_json = form_data.get("result")

    if not all([doc_id, question, result_json]):
        raise HTTPException(status_code=400, detail="Requête incomplète")

    try:
        result = json.loads(result_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON mal formé dans result")

    db = SessionLocal()
    project = db.query(Project).filter(Project.id == doc_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    # Créer la question principale
    new_query = Query(
        project_id=doc_id,
        question=question,
        best_answer=result.get("best_answer")
    )
    db.add(new_query)
    db.commit()
    db.refresh(new_query)

    for alt in result.get("alternatives", []):
        answer = Answer(
            query_id=new_query.id,
            response=alt.get("response"),
            score=alt.get("score"),
            summary=alt.get("summary"),
            page_number=alt.get("page_number"),
            chunk_id=alt.get("chunk_id"),
            excerpt=alt.get("chunk_text")
        )
        db.add(answer)

    db.commit()
    return {"message": f"✅ Question '{question}' ajoutée au projet {doc_id}"}


@app.post("/train/")
def trigger_training():
    """
    Trigger the training of the CrossEncoder model using stored feedback data.
    :return: A message indicating the training status.
    """
    if not os.path.exists(FEEDBACK_FILE):
        return {"status": "no_feedback_file"}

    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        feedback_count = sum(1 for _ in f)

    if feedback_count < TRAIN_THRESHOLD:
        return {"status": "not_enough_feedback", "count": feedback_count}

    # Lance le script d'entraînement
    try:
        subprocess.run(["python3", "train_cross_encoder.py"], check=True)
        return {"status": "training_started", "feedback_used": feedback_count}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": str(e)}


@app.get("/highlight/")
def highlight(doc_id: str, chunk_id: int):
    return highlight_chunk(doc_id, chunk_id, documents)


@app.get("/ping/")
def ping():
    """
    Simple endpoint to check if the service is running.
    :return: A message indicating the service is running.
    """
    return {"status": "ok"}

#-----------------------------------------------------------------------------------------------
# Lancement de l'application
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
