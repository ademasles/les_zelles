# app.py
"""
Streamlit application for analyzing calls for tenders (CCTP) using AI.
This app allows users to upload documents, analyze them, and ask questions about the content.
"""


#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
import streamlit as st
import requests
import time
from streamlit_option_menu import option_menu
from streamlit_tags import st_tags
import streamlit.components.v1 as components
import json

st.set_page_config(page_title="Analyse IA AO", layout="wide")

API_URL = "http://backend:8000"
PUBLIC_API_URL = "http://localhost:8000"


# -------- Sidebar menu --------
with st.sidebar:
    selected = option_menu(
        "Menu",
        ["Accueil", "Analyser un document", "Questions sur le DCE", "📁 Mes projets", "À propos", "Aide"],
        icons=["house", "file-earmark-text", "question-circle", "archive", "info-circle", "lightbulb"],
        menu_icon="cast",
        default_index=1,
    )

# -------- Fonctions utilitaires --------
def info_card(title, content):
    components.html(f"""
    <div style='background-color:#f9f9f9;padding:15px;border-radius:10px;margin:10px 0;box-shadow:2px 2px 10px rgba(0,0,0,0.05);'>
        <h4 style='color:#333;'>{title}</h4>
        <p style='font-size:15px;color:#555;'>{content}</p>
    </div>
    """, height=180)

# -------- Accueil --------
if selected == "Accueil":
    st.title("Bienvenue dans l'analyse IA des appels d'offres")
    st.markdown("""
    Cette interface permet d'analyser automatiquement des appels d'offres en détectant :
    - leur **pertinence** pour la menuiserie
    - les **critères techniques** extraits du document
    - une **synthèse structurée** pour votre agence
    """)

# -------- Analyse --------
elif selected == "Analyser un document":
    st.title("📄 Analyse IA pour appels d'offres")

    doc_id = st.text_input("Identifiant du projet", value="AO-demo")
    uploaded_file = st.file_uploader("Importer un fichier (PDF ou DOCX)", type=["pdf", "docx"])

    if uploaded_file:
        st.success(f"Fichier chargé : `{uploaded_file.name}`")

        if st.button("Analyser le document"):
            progress = st.progress(0, text="🔍 Envoi du fichier au backend...")
            start = time.perf_counter()

            try:
                # Étape 1 : envoi du fichier
                files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                upload_resp = requests.post(f"{API_URL}/upload/", files=files, data={"doc_id": doc_id})
                progress.progress(60, text="📊 Analyse des queries...")

                if upload_resp.status_code == 200:
                    st.success("✅ Fichier traité avec succès")

                    # Étape 2 : exécution des queries
                    query_resp = requests.post(f"{API_URL}/queries/", data={"doc_id": doc_id})
                    progress.progress(70, text="🧠 Génération des réponses...")

                    if query_resp.status_code == 200:
                        st.session_state.results = query_resp.json()
                        results = st.session_state.results

                        progress.progress(100, text="✅ Analyse terminée")

                        st.subheader("🧠 Synthèse par question")
                        for query_label, query_result in results.items():
                            st.markdown(f"### ❓ {query_label} ?")
                            st.markdown(f"**✅ Réponse principale :** {query_result.get('best_answer', 'Aucune réponse.')}")

                            with st.expander("🔍 Réponses similaires"):
                                for i, resp in enumerate(query_result.get("alternatives", [])):
                                    with st.expander(f"🧩 Alternative {i+1}"):
                                        st.markdown(f"""
                                        **✅ Réponse :**  
                                        {resp['response']}

                                        **📊 Score :** `{resp['score']:.3f}`  
                                        **📄 Page :** `{resp['page_number']}`
                                        """)

                                        st.markdown("**🧠 Synthèse du segment :**")
                                        st.info(resp.get('summary', 'Aucune synthèse disponible.'))


                                        url = f"{PUBLIC_API_URL}/highlight/?doc_id={doc_id}&page={resp['page_number']}&chunk_id={resp.get('chunk_id', i)}"

                                        st.link_button("🔎 Voir dans le document", url=url)

                                        user_score = st.slider("⚖️ Pertinence ?", 0.0, 1.0, 0.5, 0.1, key=f"slider_{doc_id}_{query_label}_{i}")
                                        if st.button("💾 Enregistrer feedback", key=f"save_{doc_id}_{query_label}_{i}"):
                                            feedback = {
                                                "question": query_result.get("question", query_label),
                                                "response": resp["response"],
                                                "score": user_score
                                            }
                                            fb_response = requests.post(f"{API_URL}/feedback/", json=feedback)
                                            if fb_response.status_code == 200:
                                                st.success("✅ Feedback enregistré")
                                            else:
                                                st.error("❌ Échec de l'enregistrement du feedback")
                    else:
                        st.error("❌ Échec de l'analyse des questions.")
                else:
                    st.error("❌ Problème lors du traitement du fichier.")
            except Exception as e:
                st.exception(f"❌ Erreur inattendue : {e}")
            finally:
                st.caption(f"⏱️ Temps total : {time.perf_counter() - start:.2f}s")

        if st.button("💾 Sauvegarder ce projet"):
            if "results" in st.session_state:

                payload = {
                    "doc_id": doc_id,
                    "name": uploaded_file.name,
                    "results": json.dumps(st.session_state.results)
                }

                save_resp = requests.post(f"{API_URL}/save/", data=payload)
                if save_resp.status_code == 200:
                    st.success("✅ Projet et questions sauvegardés")
                else:
                    st.error("❌ Échec de la sauvegarde")
            else:
                st.error("❌ Pas de résultats d'analyse disponibles à sauvegarder")


# -------- QA --------
elif selected == "Questions sur le DCE":
    st.title("❓ Poser une question sur le CCTP")
    doc_id = st.text_input("ID du projet (doit être préalablement analysé)", value="AO-demo")
    question = st.text_input("Votre question :")

    if st.button("Poser la question") and question:
        with st.spinner("Recherche de réponse..."):
            response = requests.post(f"{API_URL}/query/", data={"doc_id": doc_id, "question": question})

            if response.status_code == 200:
                query_result = response.json()
                st.markdown(f"### ❓ {query_result.get('question', question)}")
                st.markdown(f"**✅ Réponse principale :** {query_result.get('best_answer', 'Aucune réponse.')}")

                with st.expander("🔍 Réponses similaires"):
                    for i, resp in enumerate(query_result.get("alternatives", [])):
                        with st.expander(f"🧩 Alternative {i+1}"):
                            st.markdown(f"""
                            **✅ Réponse :**  
                            {resp['response']}

                            **📊 Score :** `{resp['score']:.3f}`  
                            **📄 Page :** `{resp['page_number']}`  
                            """)

                            st.markdown("**🧠 Synthèse du segment :**")
                            st.info(resp.get("summary", "Aucune synthèse disponible."))

                            url = f"{PUBLIC_API_URL}/highlight/?doc_id={doc_id}&page={resp['page_number']}&chunk_id={resp.get('chunk_id', i)}"
                            st.link_button("🔎 Voir dans le document", url=url)

                            user_score = st.slider("⚖️ Pertinence ?", 0.0, 1.0, 0.5, 0.1, key=f"slider_{doc_id}_{question}_{i}")
                            if st.button("💾 Enregistrer feedback", key=f"save_{doc_id}_{question}_{i}"):
                                feedback = {
                                    "question": query_result.get("question", question),
                                    "response": resp["response"],
                                    "score": user_score
                                }
                                fb_response = requests.post(f"{API_URL}/feedback/", json=feedback)
                                if fb_response.status_code == 200:
                                    st.success("✅ Feedback enregistré")
                                else:
                                    st.error("❌ Échec de l'enregistrement du feedback")

                # 💾 Ajouter cette question au projet
                if st.button("💾 Ajouter cette question au projet"):
                    payload = {
                        "doc_id": doc_id,
                        "question": query_result.get("question", question),
                        "result": json.dumps(query_result)
                    }
                    save_resp = requests.post(f"{API_URL}/project_queries/add", data=payload)

                    if save_resp.status_code == 200:
                        st.success("✅ Question ajoutée au projet avec succès.")
                    else:
                        st.error(f"❌ Erreur backend : {save_resp.status_code} — {save_resp.text}")




# -------- Historique --------
elif selected == "📁 Mes projets":
    st.title("📁 Historique des projets")
    response = requests.get(f"{API_URL}/projects/")
    if response.status_code == 200:
        projets = response.json()
        if not projets:
            st.info("Aucun projet encore sauvegardé.")
        else:
            for projet in projets:
                doc_id = projet["id"]
                with st.expander(f"📄 {projet['name']} — {doc_id}"):
                    st.markdown(f"🕒 Upload : `{projet['uploaded_at']}`")
                    st.markdown(f"**🧠 Synthèse IA :**")
                    st.info(projet.get("summary", "Aucune synthèse disponible."))

                    # 🔄 Charger les réponses sauvegardées
                    resp_detail = requests.get(f"{API_URL}/project_queries/{doc_id}")
                    if resp_detail.status_code == 200:
                        results = resp_detail.json()

                        for query_label, query_result in results.items():
                            st.markdown(f"### ❓ {query_label}")
                            st.markdown(f"**✅ Réponse principale :** {query_result['best_answer']}")

                            with st.expander("🔍 Réponses similaires"):
                                for i, resp in enumerate(query_result.get("alternatives", [])):
                                    st.markdown(f"""
                                    **✅ Réponse :**  
                                    {resp['response']}

                                    **📊 Score :** `{resp['score']:.3f}`  
                                    **📄 Page :** `{resp['page_number']}`
                                    """)

                                    st.markdown("**🧠 Synthèse du segment :**")
                                    st.info(resp.get('summary', 'Aucune synthèse disponible.'))



                                    url = f"{PUBLIC_API_URL}/highlight/?doc_id={doc_id}&page={resp['page_number']}&chunk_id={resp.get('chunk_id', i)}"
                                    st.link_button("🔎 Voir dans le document", url=url)

                    else:
                        st.warning("⚠️ Pas de réponses détaillées sauvegardées.")
    else:
        st.error("Erreur lors du chargement des projets.")


# -------- À propos --------
elif selected == "À propos":
    st.title("ℹ️ À propos")
    st.markdown("""
    Projet d'analyse IA d'appels d'offres pour la menuiserie \n
    - Construit avec **Python**, **FastAPI**, **Hugging Face**, **Ollama**, **Streamlit** \n
    - Réalisé par Anton DEMASLES \n
    - Contact : [demaslesa@gmail.com](mailto:demaslesa@gmail.com)
    """)

# -------- Aide --------
elif selected == "Aide":
    st.title("💡 Aide")
    st.markdown("""
    1. Importez un PDF ou DOCX \n
    2. Cliquez sur "Analyser" \n
    3. Consultez les critères extraits ou posez une question \n
    4. Retrouver votre historique dans l'onglet "Mes projets" \n
    """)