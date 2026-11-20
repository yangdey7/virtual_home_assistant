"""DistilBERT encoder with separate intent and device classification heads."""

from torch import nn
from torch.nn.functional import cross_entropy
from transformers import DistilBertConfig, DistilBertModel, DistilBertPreTrainedModel


class DistilBertForIntentAndDevice(DistilBertPreTrainedModel):
    config_class = DistilBertConfig

    def __init__(self, config):
        super().__init__(config)
        self.distilbert = DistilBertModel(config)
        self.dropout = nn.Dropout(config.seq_classif_dropout)
        self.intent_classifier = nn.Linear(config.dim, config.num_labels)
        self.device_classifier = nn.Linear(config.dim, len(config.device_id2label))
        self.post_init()

    def forward(self, input_ids, attention_mask=None, intent_labels=None, device_labels=None):
        encoded = self.distilbert(input_ids=input_ids, attention_mask=attention_mask)
        command = self.dropout(encoded.last_hidden_state[:, 0])
        intent_logits = self.intent_classifier(command)
        device_logits = self.device_classifier(command)
        outputs = {"intent_logits": intent_logits, "device_logits": device_logits}
        if intent_labels is not None and device_labels is not None:
            intent_loss = cross_entropy(intent_logits, intent_labels)
            device_loss = cross_entropy(device_logits, device_labels)
            outputs["loss"] = (intent_loss + device_loss) / 2
        return outputs
