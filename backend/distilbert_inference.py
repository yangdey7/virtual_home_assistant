"""Inference for the fine-tuned DistilBERT intent export and its device rules."""

import json
import re

from .codemix_inference import temperature_value
from .device_manager import ALLOWED, INTENTS


class DistilBertPredictor:
    def __init__(self, artifact_dir):
        weights = artifact_dir / "model.safetensors"
        if not weights.is_file():
            raise FileNotFoundError(f"Missing fine-tuned DistilBERT weights: {weights}")

        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        device_config = json.loads((artifact_dir / "device_config.json").read_text(encoding="utf-8"))
        self.max_length = device_config["max_length"]
        keywords = device_config["device_keywords"]
        if keywords.keys() != ALLOWED.keys():
            raise ValueError("The DistilBERT device rules must name all four supported devices.")
        self.device_patterns = {
            device: re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, aliases)) + r")(?!\w)", re.IGNORECASE)
            for device, aliases in keywords.items()
        }
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(artifact_dir, local_files_only=True)
        self.model, loading_info = AutoModelForSequenceClassification.from_pretrained(
            artifact_dir, local_files_only=True, use_safetensors=True, output_loading_info=True,
        )
        self.intent_labels = self.model.config.id2label
        if (self.model.config.model_type != "distilbert"
                or set(self.intent_labels) != set(range(len(INTENTS)))
                or set(self.intent_labels.values()) != INTENTS):
            raise ValueError("The checkpoint must be DistilBERT with the nine supported intent labels.")
        if loading_info["missing_keys"] or loading_info["mismatched_keys"]:
            raise ValueError("The DistilBERT export must contain all trained model weights.")
        self.model.eval()

    def predict(self, text):
        text = " ".join(text.split())
        inputs = self.tokenizer(
            text, truncation=True, max_length=self.max_length, return_tensors="pt", return_token_type_ids=False,
        )
        with self.torch.inference_mode():
            score, intent_id = self.model(**inputs).logits.softmax(dim=-1).max(dim=-1)
        intent = self.intent_labels[intent_id.item()]
        devices = [device for device, pattern in self.device_patterns.items() if pattern.search(text)]
        return {
            "intent": intent,
            "device": devices[0] if len(devices) == 1 else None,
            "value": temperature_value(text) if intent == "SetTemp" else None,
            "confidence": score.item(),
        }


def load_predictor(artifact_dir):
    return DistilBertPredictor(artifact_dir)
