"""
Streamlit application for analyzing calls for tenders (CCTP) using AI.
Calls backend APIs only — no direct parsing, LLM, or DB access.
"""

import json
import time

import streamlit as st
from streamlit_option_menu import option_menu

import api_client as api

st.set_page_config(page_title="Analyse IA AO", layout="wide")


with st.sidebar:
    selected = option_menu(
        "Menu",
        ["Accueil", "Analyser un document", "Questions sur le DCE", "Mes projets", "A propos", "Aide"],
        icons=["house", "file-earmark-text", "question-circle", "archive", "info-circle", "lightbulb"],
        menu_icon="cast",
        default_index=1,
    )

if selected == "Accueil":
    st.title("Bienvenue dans l'analyse IA des appels d'offres")
    st.markdown("""
    Cette interface permet d'analyser automatiquement des appels d'offres en detectant :
    - leur **pertinence** pour la menuiserie
    - les **criteres techniques** extraits du document
    - une **synthese structuree** pour votre agence
    """)

elif selected == "Analyser un document":
    st.title("Analyse IA pour appels d'offres")

    doc_id = st.text_input("Identifiant du projet", value="AO-demo")
    uploaded_file = st.file_uploader("Importer un fichier (PDF ou DOCX)", type=["pdf", "docx"])

    if uploaded_file:
        st.success(f"Fichier charge : `{uploaded_file.name}`")

        if st.button("Analyser le document"):
            progress = st.progress(0, text="Envoi du fichier au backend...")
            start = time.perf_counter()

            try:
                content = uploaded_file.read()
                upload_resp = api.upload_file(content, uploaded_file.name, doc_id)
                progress.progress(60, text="Analyse des questions...")

                if "num_chunks" in upload_resp or "doc_id" in upload_resp:
                    st.success("Fichier traite avec succes")

                    query_resp = api.run_queries(doc_id)
                    progress.progress(70, text="Generation des reponses...")

                    st.session_state.results = query_resp
                    results = st.session_state.results

                    progress.progress(100, text="Analyse terminee")

                    st.subheader("Synthese par question")
                    for query_label, query_result in results.items():
                        st.markdown(f"### {query_label} ?")
                        st.markdown(f"**Reponse principale :** {query_result.get('best_answer', 'Aucune reponse.')}")

                        with st.expander("Reponses similaires"):
                            for i, resp in enumerate(query_result.get("alternatives", [])):
                                st.markdown(f"""
                                **Reponse :** {resp['response']}
                                **Score :** `{resp['score']:.3f}`
                                **Page :** `{resp['page_number']}`
                                """)
                                if "bboxes" in resp and resp["bboxes"]:
                                    st.json(resp["bboxes"])
                                st.markdown("**Synthese du segment :**")
                                st.info(resp.get('summary', 'Aucune synthese disponible.'))

                                user_score = st.slider(
                                    "Pertinence ?", 0.0, 1.0, 0.5, 0.1,
                                    key=f"slider_{doc_id}_{query_label}_{i}"
                                )
                                if st.button("Enregistrer feedback", key=f"save_{doc_id}_{query_label}_{i}"):
                                    try:
                                        api.submit_feedback(
                                            query_result.get("question", query_label),
                                            resp["response"],
                                            user_score,
                                        )
                                        st.success("Feedback enregistre")
                                    except Exception:
                                        st.error("Echec de l'enregistrement du feedback")
                else:
                    st.error("Probleme lors du traitement du fichier.")
            except Exception as e:
                st.exception(f"Erreur inattendue : {e}")
            finally:
                st.caption(f"Temps total : {time.perf_counter() - start:.2f}s")

        if st.button("Sauvegarder ce projet"):
            if "results" in st.session_state:
                try:
                    api.save_project(doc_id, uploaded_file.name, json.dumps(st.session_state.results))
                    st.success("Projet et questions sauvegardes")
                except Exception as e:
                    st.error(f"Echec de la sauvegarde : {e}")
            else:
                st.error("Pas de resultats d'analyse disponibles a sauvegarder")

elif selected == "Questions sur le DCE":
    st.title("Poser une question sur le CCTP")
    doc_id = st.text_input("ID du projet (doit etre prealablement analyse)", value="AO-demo")
    question = st.text_input("Votre question :")

    if st.button("Poser la question") and question:
        with st.spinner("Recherche de reponse..."):
            try:
                query_result = api.ask_question(doc_id, question)
                st.markdown(f"### {query_result.get('question', question)}")
                st.markdown(f"**Reponse principale :** {query_result.get('best_answer', 'Aucune reponse.')}")

                with st.expander("Reponses similaires"):
                    for i, resp in enumerate(query_result.get("alternatives", [])):
                        st.markdown(f"""
                        **Reponse :** {resp['response']}
                        **Score :** `{resp['score']:.3f}`
                        **Page :** `{resp['page_number']}`
                        """)
                        if "bboxes" in resp and resp["bboxes"]:
                            st.json(resp["bboxes"])
                        st.markdown("**Synthese du segment :**")
                        st.info(resp.get("summary", "Aucune synthese disponible."))

                        user_score = st.slider(
                            "Pertinence ?", 0.0, 1.0, 0.5, 0.1,
                            key=f"slider_{doc_id}_{question}_{i}"
                        )
                        if st.button("Enregistrer feedback", key=f"save_{doc_id}_{question}_{i}"):
                            try:
                                api.submit_feedback(
                                    query_result.get("question", question),
                                    resp["response"],
                                    user_score,
                                )
                                st.success("Feedback enregistre")
                            except Exception:
                                st.error("Echec de l'enregistrement du feedback")

                if st.button("Ajouter cette question au projet"):
                    try:
                        api.add_question_to_project(doc_id, query_result.get("question", question),
                                                    json.dumps(query_result))
                        st.success("Question ajoutee au projet avec succes.")
                    except Exception as e:
                        st.error(f"Erreur : {e}")

            except Exception as e:
                st.error(f"Erreur lors de la requete : {e}")

elif selected == "Mes projets":
    st.title("Historique des projets")
    try:
        projets = api.list_projects()
        if not projets:
            st.info("Aucun projet encore sauvegarde.")
        else:
            for projet in projets:
                doc_id = projet["id"]
                with st.expander(f"{projet['name']} - {doc_id}"):
                    st.markdown(f"Upload : `{projet.get('uploaded_at', 'N/A')}`")
                    st.markdown("**Synthese IA :**")
                    st.info(projet.get("summary", "Aucune synthese disponible."))

                    try:
                        results = api.get_project_queries(doc_id)
                        for query_label, query_result in results.items():
                            st.markdown(f"### {query_label}")
                            st.markdown(f"**Reponse principale :** {query_result['best_answer']}")
                            with st.expander("Reponses similaires"):
                                for i, resp in enumerate(query_result.get("alternatives", [])):
                                    st.markdown(f"""
                                    **Reponse :** {resp['response']}
                                    **Score :** `{resp['score']:.3f}`
                                    **Page :** `{resp['page_number']}`
                                    """)
                                    st.markdown("**Synthese du segment :**")
                                    st.info(resp.get('summary', 'Aucune synthese disponible.'))
                    except Exception:
                        st.warning("Pas de reponses detaillees sauvegardees.")
    except Exception as e:
        st.error(f"Erreur lors du chargement des projets : {e}")

elif selected == "A propos":
    st.title("A propos")
    st.markdown("""
    Projet d'analyse IA d'appels d'offres pour la menuiserie
    - Construit avec **Python**, **FastAPI**, **Hugging Face**, **Ollama**, **Streamlit**
    - Realise par Anton DEMASLES
    - Contact : demaslesa@gmail.com
    """)

elif selected == "Aide":
    st.title("Aide")
    st.markdown("""
    1. Importez un PDF ou DOCX
    2. Cliquez sur "Analyser"
    3. Consultez les criteres extraits ou posez une question
    4. Retrouvez votre historique dans l'onglet "Mes projets"
    """)
