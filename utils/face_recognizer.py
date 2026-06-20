import cv2
import numpy as np
import pickle
from sklearn.metrics.pairwise import cosine_similarity

DB_PATH = "embeddings/users.pkl"
INDEX_PATH = "embeddings/trained_index.pkl"

def load_db():

    try:
        with open(DB_PATH, "rb") as f:
            return pickle.load(f)

    except:
        return {}

def save_db(data):

    with open(DB_PATH, "wb") as f:
        pickle.dump(data, f)

def train_model():

    db = load_db()

    if not db:
        with open(INDEX_PATH, "wb") as f:
            pickle.dump({"labels": [], "embeddings": np.empty((0, 49152), dtype=np.float32)}, f)
        return

    labels = list(db.keys())
    embeddings = np.array([db[label] for label in labels], dtype=np.float32)

    with open(INDEX_PATH, "wb") as f:
        pickle.dump({"labels": labels, "embeddings": embeddings}, f)

def load_trained_index():

    try:
        with open(INDEX_PATH, "rb") as f:
            return pickle.load(f)
    except:
        train_model()
        with open(INDEX_PATH, "rb") as f:
            return pickle.load(f)

def get_embedding(face):

    resized = cv2.resize(face, (128,128))

    emb = resized.flatten()
    norm = np.linalg.norm(emb)
    if norm == 0:
        return emb.astype(np.float32)
    emb = emb / norm

    return emb.astype(np.float32)

def register_face(name, face):

    db = load_db()

    db[name] = get_embedding(face)

    save_db(db)
    train_model()

def recognize(face):
    trained = load_trained_index()
    labels = trained["labels"]
    embeddings = trained["embeddings"]

    current = get_embedding(face)

    best_name = "Unknown"
    best_score = 0

    for idx, name in enumerate(labels):
        emb = embeddings[idx]

        similarity = cosine_similarity(
            [current],
            [emb]
        )[0][0]

        if similarity > best_score:

            best_score = similarity
            best_name = name

    return best_name, float(best_score)
