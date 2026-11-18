"""Inference for the supplied XLM-R intent and device checkpoints."""

import re


# The exports contain generic LABEL_n entries. These IDs were matched against
# English and code-mixed commands in the supplied Whisper evaluation CSV.
INTENT_LABELS = (
    "Close", "DecreaseSpeed", "DecreaseTemp", "IncreaseSpeed", "IncreaseTemp",
    "Open", "SetTemp", "TurnOff", "TurnOn",
)
DEVICE_LABELS = ("AC", "Curtain", "Fan", "Light")

SMALL_NUMBERS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20),
))
TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
UNITS = "|".join(word for word, value in SMALL_NUMBERS.items() if 1 <= value <= 9)
TEMPERATURE = re.compile(
    rf"(?<![\w.])(?:(?:minus|negative)\s+)?[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?!\d)"
    rf"|\b(?:(?:minus|negative)\s+)?(?:(?:{'|'.join(TENS)})(?:(?:\s+|-)(?:{UNITS}))?"
    rf"|(?:{'|'.join(SMALL_NUMBERS)}))\b",
    re.IGNORECASE,
)


def temperature_value(text):
    matches = TEMPERATURE.findall(text)
    if len(matches) != 1:
        return None
    value = matches[0]
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    words = value.lower().replace("-", " ").split()
    if words[0] in ("minus", "negative"):
        return None
    if words[0] in TENS:
        return TENS[words[0]] + (SMALL_NUMBERS[words[1]] if len(words) == 2 else 0)
    return SMALL_NUMBERS.get(words[0])


class CodeMixPredictor:
    def __init__(self, artifact_dir):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        intent_dir = artifact_dir / "intent_model" / "checkpoint-260"
        device_dir = artifact_dir / "best_device_model"
        self.torch = torch
        self.device_tokenizer = AutoTokenizer.from_pretrained(device_dir, local_files_only=True)
        # The intent checkpoint ships without a tokenizer. Reuse the matching
        # XLM-R tokenizer from the device export unless one is supplied.
        self.intent_tokenizer = self.device_tokenizer
        if (intent_dir / "tokenizer.json").is_file():
            self.intent_tokenizer = AutoTokenizer.from_pretrained(intent_dir, local_files_only=True)
        self.intent_model = AutoModelForSequenceClassification.from_pretrained(
            intent_dir, local_files_only=True, use_safetensors=True,
        ).eval()
        self.device_model = AutoModelForSequenceClassification.from_pretrained(
            device_dir, local_files_only=True, use_safetensors=True,
        ).eval()
        if (self.intent_model.config.num_labels != len(INTENT_LABELS)
                or self.device_model.config.num_labels != len(DEVICE_LABELS)):
            raise ValueError("The supplied checkpoint heads must have nine intent and four device labels.")

    def predict(self, text):
        device_inputs = self.device_tokenizer(text, truncation=True, return_tensors="pt")
        intent_inputs = device_inputs
        if self.intent_tokenizer is not self.device_tokenizer:
            intent_inputs = self.intent_tokenizer(text, truncation=True, return_tensors="pt")
        with self.torch.inference_mode():
            intent_score, intent_id = self.intent_model(**intent_inputs).logits.softmax(dim=-1).max(dim=-1)
            device_score, device_id = self.device_model(**device_inputs).logits.softmax(dim=-1).max(dim=-1)
        intent = INTENT_LABELS[intent_id.item()]
        return {
            "intent": intent,
            "device": DEVICE_LABELS[device_id.item()],
            "value": temperature_value(text) if intent == "SetTemp" else None,
            "confidence": min(intent_score.item(), device_score.item()),
        }


def load_predictor(artifact_dir):
    return CodeMixPredictor(artifact_dir)
