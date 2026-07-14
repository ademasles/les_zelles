# train_cross_encoder.py
"""Train a CrossEncoder model using user feedback data."""



#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
from sentence_transformers import CrossEncoder, InputExample
from torch.utils.data import DataLoader
import json

from app.core.config import settings

FEEDBACK_FILE = settings.feedback_file
MODEL_OUTPUT_DIR = settings.cross_encoder_output_dir


#-----------------------------------------------------------------------------------------------
# FUNCTIONS
#-----------------------------------------------------------------------------------------------
def load_feedback_data():
    """
    Load feedback data from the JSONL file and convert it to InputExample format.
    :return: List of InputExample objects.
    """
    examples = []
    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            examples.append(InputExample(texts=[entry["question"], entry["response"]], label=entry["score"]))
    return examples

def train():
    """
    Train the CrossEncoder model using the loaded feedback data.
    Saves the trained model to the specified output directory.
    """
    print("📚 Chargement des feedbacks...")
    data = load_feedback_data()
    model = CrossEncoder(settings.cross_encoder_model, num_labels=1)

    loader = DataLoader(data, shuffle=True, batch_size=8)
    model.fit(train_dataloader=loader, epochs=1)

    print(f"💾 Sauvegarde dans {MODEL_OUTPUT_DIR}")
    model.save(str(MODEL_OUTPUT_DIR))

if __name__ == "__main__":
    train()
