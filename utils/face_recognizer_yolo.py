import os
import cv2
import numpy as np
import shutil
import threading
from ultralytics import YOLO

# Paths — single runtime model; base weights used only during training
DATASET_PATH = "dataset"
MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "yolov8s_face_classifier.pt")
PRETRAINED_CLS_PATH = os.path.join(MODEL_DIR, "yolov8s-cls.pt")
MIN_CONFIDENCE = 0.78
MIN_CONFIDENCE_MARGIN = 0.08

# Global trainer state
class FaceTrainer:
    def __init__(self):
        self.is_training = False
        self.active_model = None
        self.load_active_model()

    def load_active_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                self.active_model = YOLO(MODEL_PATH)
                print("[FaceEngine] Loaded custom YOLOv8s face classifier.")
            except Exception as e:
                print(f"[FaceEngine] Failed to load custom classifier: {e}")
                self.active_model = None
        else:
            self.active_model = None
            print("[FaceEngine] No custom classifier found. Ready for first registration.")

    def get_folder_name(self, embedding_key):
        # Sanitize for Windows folder compatibility
        return embedding_key.replace("|", "__").replace(":", "_").replace("/", "_").replace("\\", "_")

    def get_embedding_key(self, folder_name):
        return folder_name.replace("__", "|")

    def generate_background_class(self):
        train_bg = os.path.join(DATASET_PATH, "train", "background")
        val_bg = os.path.join(DATASET_PATH, "val", "background")
        os.makedirs(train_bg, exist_ok=True)
        os.makedirs(val_bg, exist_ok=True)

        # Generate 20 synthetic training background images
        if len(os.listdir(train_bg)) < 15:
            for i in range(20):
                img = np.zeros((128, 128, 3), dtype=np.uint8)
                # Random gradients
                c1 = np.random.randint(50, 200, 3)
                c2 = np.random.randint(50, 200, 3)
                for y in range(128):
                    alpha = y / 128.0
                    img[y, :] = (1 - alpha) * c1 + alpha * c2
                # Random shapes
                for _ in range(5):
                    center = (np.random.randint(20, 108), np.random.randint(20, 108))
                    radius = np.random.randint(10, 35)
                    color = tuple(map(int, np.random.randint(50, 255, 3)))
                    cv2.circle(img, center, radius, color, -1)
                # Add noise
                noise = np.random.normal(0, 15, img.shape).astype(np.int16)
                img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
                cv2.imwrite(os.path.join(train_bg, f"bg_{i}.jpg"), img)

        # Generate 5 validation background images
        if len(os.listdir(val_bg)) < 4:
            for i in range(5):
                img = np.zeros((128, 128, 3), dtype=np.uint8)
                c1 = np.random.randint(50, 200, 3)
                c2 = np.random.randint(50, 200, 3)
                for y in range(128):
                    alpha = y / 128.0
                    img[y, :] = (1 - alpha) * c1 + alpha * c2
                noise = np.random.normal(0, 15, img.shape).astype(np.int16)
                img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
                cv2.imwrite(os.path.join(val_bg, f"bg_val_{i}.jpg"), img)

    def augment_crop(self, img, output_dir, prefix, count=5):
        os.makedirs(output_dir, exist_ok=True)
        h, w = img.shape[:2]

        # Save original crop
        cv2.imwrite(os.path.join(output_dir, f"{prefix}_orig.jpg"), img)

        idx = 1
        # Rotations
        for angle in [-15, -10, -5, 5, 10, 15]:
            if idx >= count:
                break
            M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
            rotated = cv2.warpAffine(img, M, (w, h))
            cv2.imwrite(os.path.join(output_dir, f"{prefix}_rot_{angle}.jpg"), rotated)
            idx += 1

        # Brightness alterations
        for brightness in [0.75, 0.85, 1.15, 1.25]:
            if idx >= count:
                break
            adjusted = cv2.convertScaleAbs(img, alpha=brightness, beta=0)
            cv2.imwrite(os.path.join(output_dir, f"{prefix}_bright_{brightness}.jpg"), adjusted)
            idx += 1

        # Contrast alterations (helps with different camera/lighting setups)
        for beta in [-20, 20]:
            if idx >= count:
                break
            adjusted = cv2.convertScaleAbs(img, alpha=1.0, beta=beta)
            cv2.imwrite(os.path.join(output_dir, f"{prefix}_contrast_{beta}.jpg"), adjusted)
            idx += 1

        # Slight gaussian blur (simulates camera focus/motion variance)
        if idx < count:
            blurred = cv2.GaussianBlur(img, (3, 3), 0)
            cv2.imwrite(os.path.join(output_dir, f"{prefix}_blur.jpg"), blurred)
            idx += 1

        # Scale jitter (zoom in/out slightly — crops vary in tightness in practice)
        for scale in [0.9, 1.1]:
            if idx >= count:
                break
            M = cv2.getRotationMatrix2D((w/2, h/2), 0, scale)
            scaled = cv2.warpAffine(img, M, (w, h))
            cv2.imwrite(os.path.join(output_dir, f"{prefix}_scale_{scale}.jpg"), scaled)
            idx += 1

        # Small translation jitter (face not perfectly centered in box)
        for dx, dy in [(8, 0), (-8, 0)]:
            if idx >= count:
                break
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            shifted = cv2.warpAffine(img, M, (w, h))
            cv2.imwrite(os.path.join(output_dir, f"{prefix}_shift_{dx}_{dy}.jpg"), shifted)
            idx += 1

        # Flip (only if not a side profile, but for classification identity is fine)
        if idx < count:
            flipped = cv2.flip(img, 1)
            cv2.imwrite(os.path.join(output_dir, f"{prefix}_flip.jpg"), flipped)
            idx += 1

    def start_background_training(self):
        if self.is_training:
            print("[FaceEngine] Training already in progress. Skipping duplicate request.")
            return
        thread = threading.Thread(target=self._run_training)
        thread.daemon = True
        thread.start()

    def _run_training(self):
        self.is_training = True
        print("[FaceEngine] Background training started...")
        try:
            # Generate background class
            self.generate_background_class()
            
            # Check classes
            train_dir = os.path.join(DATASET_PATH, "train")
            classes = [d for d in os.listdir(train_dir) if os.path.isdir(os.path.join(train_dir, d))]
            if len(classes) < 2:
                print("[FaceEngine] Not enough classes to train (minimum 2 classes required, including background).")
                return

            # Clean previous runs
            if os.path.exists("runs"):
                try:
                    shutil.rmtree("runs")
                except Exception as e:
                    print(f"[FaceEngine] Warning: failed to clear runs directory: {e}")

            # Initialize and train from local base weights when available
            pretrained = PRETRAINED_CLS_PATH if os.path.exists(PRETRAINED_CLS_PATH) else "yolov8s-cls.pt"
            num_classes = len(classes)
            # Train longer and unfreeze more of the backbone — with only a
            # handful of images per class, freeze=9 left too little of the
            # network trainable to separate faces from "background"/each
            # other confidently.
            epochs = min(60, max(25, 15 + num_classes * 2))
            model = YOLO(pretrained)
            model.train(
                data=os.path.abspath(DATASET_PATH),
                epochs=epochs,
                imgsz=128,
                device="cpu",
                workers=0,
                freeze=4,
                verbose=False,
                patience=12,
                degrees=10,
                hsv_v=0.3,
                hsv_s=0.3,
            )

            # Copy weight file
            best_weights = "runs/classify/train/weights/best.pt"
            if os.path.exists(best_weights):
                os.makedirs(MODEL_DIR, exist_ok=True)
                shutil.copy(best_weights, MODEL_PATH)
                print(f"[FaceEngine] Model trained successfully and weights saved to {MODEL_PATH}")
                # Reload model
                self.load_active_model()
            else:
                print("[FaceEngine] Training completed but best weights file not found.")

        except Exception as e:
            print(f"[FaceEngine] Training failed with error: {e}")
        finally:
            # Clean up runs folder
            if os.path.exists("runs"):
                try:
                    shutil.rmtree("runs")
                except Exception as e:
                    pass
            self.is_training = False
            print("[FaceEngine] Background training process finished.")

# Global instance
engine = FaceTrainer()

def recognize(face_img):
    if engine.active_model is None:
        return "Unknown", 0.0

    try:
        # Resize input face to 128x128
        face_resized = cv2.resize(face_img, (128, 128))
        results = engine.active_model(face_resized, verbose=False)
        if len(results) == 0 or results[0].probs is None:
            return "Unknown", 0.0

        probs = results[0].probs
        top1_idx = probs.top1
        top1_conf = float(probs.top1conf)
        class_name = results[0].names[top1_idx]

        if class_name == "background" or top1_conf < MIN_CONFIDENCE:
            return "Unknown", top1_conf

        # Reject ambiguous matches only once there are multiple real
        # identities that could actually be confused with each other.
        # Background must be excluded from this comparison — otherwise
        # "person vs background" gets misread as "which person is this?"
        # ambiguity and falsely rejects confident, unambiguous matches.
        names = results[0].names
        real_confs = [
            float(probs.data[i]) for i in range(len(probs.data))
            if names[i] != "background"
        ]
        if len(real_confs) >= 2:
            sorted_conf = sorted(real_confs, reverse=True)
            if (sorted_conf[0] - sorted_conf[1]) < MIN_CONFIDENCE_MARGIN:
                return "Unknown", top1_conf

        embedding_key = engine.get_embedding_key(class_name)
        return embedding_key, top1_conf
    except Exception as e:
        print(f"[FaceEngine] Inference error: {e}")
        return "Unknown", 0.0

def register_face(embedding_key, face_crop):
    """
    Register a face from a single image (backward compatibility).
    """
    sanitized_key = engine.get_folder_name(embedding_key)
    train_dir = os.path.join(DATASET_PATH, "train", sanitized_key)
    val_dir = os.path.join(DATASET_PATH, "val", sanitized_key)

    os.makedirs(train_dir, exist_ok=True)
    os.makedirs(val_dir, exist_ok=True)

    # Augment crops: 24 training, 6 validation
    engine.augment_crop(face_crop, train_dir, "single_t", count=24)
    engine.augment_crop(face_crop, val_dir, "single_v", count=6)

    # Start training
    engine.start_background_training()

def register_face_multi(embedding_key, phone):
    """
    Register a face using the 4 captured images from the multi-stage registration process.
    """
    sanitized_key = engine.get_folder_name(embedding_key)
    train_dir = os.path.join(DATASET_PATH, "train", sanitized_key)
    val_dir = os.path.join(DATASET_PATH, "val", sanitized_key)

    # Clear existing images for this class to prevent carryover
    if os.path.exists(train_dir):
        shutil.rmtree(train_dir)
    if os.path.exists(val_dir):
        shutil.rmtree(val_dir)

    os.makedirs(train_dir, exist_ok=True)
    os.makedirs(val_dir, exist_ok=True)

    temp_dir = os.path.join(DATASET_PATH, "temp", phone)
    if not os.path.exists(temp_dir):
        print(f"[FaceEngine] Temporary registration directory {temp_dir} not found. Cannot register multi-stage faces.")
        return

    # Process all temp files: left, right, final
    temp_files = [f for f in os.listdir(temp_dir) if f.endswith(".jpg")]
    for filename in temp_files:
        filepath = os.path.join(temp_dir, filename)
        img = cv2.imread(filepath)
        if img is None:
            continue
        
        prefix = os.path.splitext(filename)[0]
        # Augment: 10 training, 3 validation images per capture stage
        engine.augment_crop(img, train_dir, f"{prefix}_train", count=10)
        engine.augment_crop(img, val_dir, f"{prefix}_val", count=3)

    # Clean up temp folder
    shutil.rmtree(temp_dir)

    # Start training
    engine.start_background_training()

def train_model():
    """
    Start/resume training based on current dataset.
    """
    engine.start_background_training()


def is_model_training():
    return engine.is_training


def remove_face_class(embedding_key):
    """Remove a person's training images and schedule model retrain."""
    sanitized_key = engine.get_folder_name(embedding_key)
    train_dir = os.path.join(DATASET_PATH, "train", sanitized_key)
    val_dir = os.path.join(DATASET_PATH, "val", sanitized_key)
    for folder in (train_dir, val_dir):
        if os.path.exists(folder):
            shutil.rmtree(folder)
    engine.start_background_training()


def rename_face_class(old_embedding_key, new_embedding_key):
    """Rename dataset folders when person identity key changes."""
    if old_embedding_key == new_embedding_key:
        return
    old_name = engine.get_folder_name(old_embedding_key)
    new_name = engine.get_folder_name(new_embedding_key)
    for split in ("train", "val"):
        old_dir = os.path.join(DATASET_PATH, split, old_name)
        new_dir = os.path.join(DATASET_PATH, split, new_name)
        if os.path.exists(old_dir):
            if os.path.exists(new_dir):
                shutil.rmtree(new_dir)
            os.rename(old_dir, new_dir)
    engine.start_background_training()