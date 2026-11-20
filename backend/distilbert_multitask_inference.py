"""Inference from the multitask DistilBERT notebook export."""

from .codemix_inference import temperature_value
from .device_manager import ALLOWED, INTENTS


class MultitaskDistilBertPredictor:
    def __init__(self, artifact_dir):
        if not (artifact_dir / "model.safetensors").is_file():
            raise FileNotFoundError(f"Missing multitask DistilBERT weights in {artifact_dir}.")

        import torch
        from transformers import AutoTokenizer, DistilBertConfig

        from .distilbert_multitask_model import DistilBertForIntentAndDevice

        config = DistilBertConfig.from_pretrained(artifact_dir, local_files_only=True)
        self.intent_labels = config.id2label
        self.device_labels = {int(index): device for index, device in config.device_id2label.items()}
        if (
            set(self.intent_labels) != set(range(len(INTENTS)))
            or set(self.intent_labels.values()) != INTENTS
            or set(self.device_labels) != set(range(len(ALLOWED)))
            or set(self.device_labels.values()) != ALLOWED.keys()
        ):
            raise ValueError("The checkpoint must have all nine intent labels and four device labels.")
        self.max_length = config.command_max_length
        if type(self.max_length) is not int or not 1 <= self.max_length <= config.max_position_embeddings:
            raise ValueError("The checkpoint has an invalid command_max_length.")

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(artifact_dir, local_files_only=True)
        self.model, loading_info = DistilBertForIntentAndDevice.from_pretrained(
            artifact_dir, config=config, local_files_only=True, use_safetensors=True, output_loading_info=True,
        )
        if loading_info["missing_keys"] or loading_info["mismatched_keys"]:
            raise ValueError("The checkpoint must include the trained encoder and both classifier heads.")
        self.model.eval()

    def predict(self, text):
        text = " ".join(text.split())
        inputs = self.tokenizer(
            text, truncation=True, max_length=self.max_length, return_tensors="pt", return_token_type_ids=False,
        )
        with self.torch.inference_mode():
            outputs = self.model(**inputs)
            intent_score, intent_id = outputs["intent_logits"].softmax(dim=-1).max(dim=-1)
            device_score, device_id = outputs["device_logits"].softmax(dim=-1).max(dim=-1)
        intent = self.intent_labels[intent_id.item()]
        return {
            "intent": intent,
            "device": self.device_labels[device_id.item()],
            "value": temperature_value(text) if intent == "SetTemp" else None,
            "confidence": min(intent_score.item(), device_score.item()),
        }


def load_predictor(artifact_dir):
    return MultitaskDistilBertPredictor(artifact_dir)
