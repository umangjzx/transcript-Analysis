"""
Fine-tune DistilBERT-MNLI on a grooming-specific NLI dataset.

This script adapts the base zero-shot classifier (typeform/distilbert-base-uncased-mnli)
to better distinguish grooming tactics by training on domain-specific premise–hypothesis
pairs in the Natural Language Inference (NLI) format.

Usage
-----
    python finetune_model.py                         # train with default settings
    python finetune_model.py --epochs 5 --lr 2e-5   # custom hyperparams
    python finetune_model.py --dataset path/to/data.json  # custom dataset

Output
------
    backend/models/grooming-nli-finetuned/
        ├── config.json
        ├── model.safetensors
        ├── tokenizer.json
        └── ...

After training, set FINETUNED_MODEL_PATH in .env to use the fine-tuned model:
    FINETUNED_MODEL_PATH=models/grooming-nli-finetuned
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "models" / "grooming-nli-finetuned"
DEFAULT_DATASET_PATH = BASE_DIR / "data" / "grooming_nli_dataset.json"

# ---------------------------------------------------------------------------
# Grooming-specific NLI training data
# ---------------------------------------------------------------------------
# Format: {"premise": str, "hypothesis": str, "label": 0|1|2}
#   0 = entailment (premise supports hypothesis)
#   1 = neutral
#   2 = contradiction (premise contradicts hypothesis)

GROOMING_NLI_SAMPLES = [
    # ── Secrecy ──────────────────────────────────────────────────────────────
    {"premise": "Don't tell your mom about our chats, okay? This is just between us.",
     "hypothesis": "asking someone to keep a secret or hide something", "label": 0},
    {"premise": "Nobody else needs to know about this. Promise me you won't say anything.",
     "hypothesis": "asking someone to keep a secret or hide something", "label": 0},
    {"premise": "Let's keep this our little secret. Your parents wouldn't understand.",
     "hypothesis": "asking someone to keep a secret or hide something", "label": 0},
    {"premise": "If you tell anyone, they'll take your phone away.",
     "hypothesis": "asking someone to keep a secret or hide something", "label": 0},
    {"premise": "I told my friend about the surprise party we're planning.",
     "hypothesis": "asking someone to keep a secret or hide something", "label": 2},
    {"premise": "The weather is nice today, let's go to the park.",
     "hypothesis": "asking someone to keep a secret or hide something", "label": 2},

    # ── Parent Monitoring ────────────────────────────────────────────────────
    {"premise": "Do your parents check your messages? Can they see what we're talking about?",
     "hypothesis": "asking if parents monitor messages", "label": 0},
    {"premise": "Does your mom read your texts? I just want to make sure we can talk freely.",
     "hypothesis": "asking if parents monitor messages", "label": 0},
    {"premise": "Are your parents strict about your phone? Do they have your password?",
     "hypothesis": "asking if parents monitor messages", "label": 0},
    {"premise": "My parents are really supportive of my hobbies.",
     "hypothesis": "asking if parents monitor messages", "label": 2},
    {"premise": "I need to call my mom to let her know I'll be late.",
     "hypothesis": "asking if parents monitor messages", "label": 2},

    # ── Trust Building ───────────────────────────────────────────────────────
    {"premise": "You can tell me anything, I'll always be here for you no matter what.",
     "hypothesis": "building emotional trust with someone", "label": 0},
    {"premise": "I feel like we have a special connection that nobody else understands.",
     "hypothesis": "building emotional trust with someone", "label": 0},
    {"premise": "You're so mature for your age. Most people don't get me like you do.",
     "hypothesis": "building emotional trust with someone", "label": 0},
    {"premise": "I'm the only one who truly understands you. Your friends don't care like I do.",
     "hypothesis": "building emotional trust with someone", "label": 0},
    {"premise": "The team meeting is scheduled for 3pm tomorrow.",
     "hypothesis": "building emotional trust with someone", "label": 2},

    # ── Manipulation ─────────────────────────────────────────────────────────
    {"premise": "If you really loved me, you would do this for me.",
     "hypothesis": "manipulating or pressuring someone", "label": 0},
    {"premise": "After everything I've done for you, you owe me this.",
     "hypothesis": "manipulating or pressuring someone", "label": 0},
    {"premise": "You're being so ungrateful. I thought we were special.",
     "hypothesis": "manipulating or pressuring someone", "label": 0},
    {"premise": "Nobody else will ever care about you the way I do.",
     "hypothesis": "manipulating or pressuring someone", "label": 0},
    {"premise": "Could you please pass me the salt?",
     "hypothesis": "manipulating or pressuring someone", "label": 2},

    # ── Meeting Request ──────────────────────────────────────────────────────
    {"premise": "We should meet up in person. I know a quiet place where nobody will see us.",
     "hypothesis": "arranging an in-person meeting", "label": 0},
    {"premise": "Can you sneak out tonight? I'll pick you up at the corner.",
     "hypothesis": "arranging an in-person meeting", "label": 0},
    {"premise": "Let's meet at the park after school. Don't tell anyone you're coming.",
     "hypothesis": "arranging an in-person meeting", "label": 0},
    {"premise": "I'm meeting my study group at the library at 4pm.",
     "hypothesis": "arranging an in-person meeting", "label": 2},

    # ── Address / Location ───────────────────────────────────────────────────
    {"premise": "Where do you live? What's your address? I want to send you something.",
     "hypothesis": "asking for a home address or location", "label": 0},
    {"premise": "Which neighborhood are you in? Is your house near the school?",
     "hypothesis": "asking for a home address or location", "label": 0},
    {"premise": "The restaurant is located at 123 Main Street.",
     "hypothesis": "asking for a home address or location", "label": 2},

    # ── Video Call / Photos ──────────────────────────────────────────────────
    {"premise": "Send me a picture of yourself. I want to see what you look like right now.",
     "hypothesis": "requesting a video call or photos", "label": 0},
    {"premise": "Let's video call tonight when your parents are asleep.",
     "hypothesis": "requesting a video call or photos", "label": 0},
    {"premise": "Can you turn on your camera? I want to see you.",
     "hypothesis": "requesting a video call or photos", "label": 0},
    {"premise": "The team will have a video conference at 2pm.",
     "hypothesis": "requesting a video call or photos", "label": 2},

    # ── School Information ───────────────────────────────────────────────────
    {"premise": "What school do you go to? What grade are you in?",
     "hypothesis": "asking about school or grade", "label": 0},
    {"premise": "What time does your school finish? Do you walk home alone?",
     "hypothesis": "asking about school or grade", "label": 0},
    {"premise": "I graduated from university in 2015 with a degree in engineering.",
     "hypothesis": "asking about school or grade", "label": 2},

    # ── Routine ──────────────────────────────────────────────────────────────
    {"premise": "What time are you usually home alone? When do your parents leave for work?",
     "hypothesis": "asking about daily routine or when someone is alone", "label": 0},
    {"premise": "Are you alone right now? When does your mom get back?",
     "hypothesis": "asking about daily routine or when someone is alone", "label": 0},
    {"premise": "I usually wake up at 7am and go for a jog.",
     "hypothesis": "asking about daily routine or when someone is alone", "label": 1},

    # ── Explicit Content ─────────────────────────────────────────────────────
    {"premise": "Have you ever touched yourself? I can teach you things.",
     "hypothesis": "sexually explicit or inappropriate content", "label": 0},
    {"premise": "What are you wearing right now? Describe it to me.",
     "hypothesis": "sexually explicit or inappropriate content", "label": 0},
    {"premise": "I wore a blue shirt and jeans to the office today.",
     "hypothesis": "sexually explicit or inappropriate content", "label": 2},

    # ── Relationship Building ────────────────────────────────────────────────
    {"premise": "I think I'm falling in love with you. You're my everything.",
     "hypothesis": "building a close or romantic relationship", "label": 0},
    {"premise": "You're my girlfriend now, right? We belong together.",
     "hypothesis": "building a close or romantic relationship", "label": 0},
    {"premise": "Age is just a number. What matters is how we feel about each other.",
     "hypothesis": "building a close or romantic relationship", "label": 0},
    {"premise": "My colleague and I are working on the quarterly report.",
     "hypothesis": "building a close or romantic relationship", "label": 2},

    # ── Safe / Normal ────────────────────────────────────────────────────────
    {"premise": "Hey, how was your day? Did you finish your homework?",
     "hypothesis": "a safe or normal conversation", "label": 0},
    {"premise": "The movie starts at 7. Want to grab dinner first?",
     "hypothesis": "a safe or normal conversation", "label": 0},
    {"premise": "I need help with my math assignment. Can you explain fractions?",
     "hypothesis": "a safe or normal conversation", "label": 0},
    {"premise": "Don't tell anyone about us. This is our secret.",
     "hypothesis": "a safe or normal conversation", "label": 2},
    {"premise": "Send me a picture when your parents aren't looking.",
     "hypothesis": "a safe or normal conversation", "label": 2},

    # ── Bad Language ─────────────────────────────────────────────────────────
    {"premise": "I'll hurt you if you don't do what I say, you little brat.",
     "hypothesis": "threatening, abusive, or offensive language", "label": 0},
    {"premise": "You're worthless. Nobody will believe you if you tell.",
     "hypothesis": "threatening, abusive, or offensive language", "label": 0},
    {"premise": "Thank you for helping me with the project, I appreciate it.",
     "hypothesis": "threatening, abusive, or offensive language", "label": 2},

    # ── Cross-category contradictions (hard negatives) ───────────────────────
    {"premise": "Don't tell your mom about our chats.",
     "hypothesis": "a safe or normal conversation", "label": 2},
    {"premise": "You can tell me anything, I'll always be here for you.",
     "hypothesis": "asking someone to keep a secret or hide something", "label": 2},
    {"premise": "What school do you go to?",
     "hypothesis": "arranging an in-person meeting", "label": 2},
    {"premise": "Let's meet at the park after school.",
     "hypothesis": "asking about school or grade", "label": 1},
    {"premise": "Are you alone right now?",
     "hypothesis": "a safe or normal conversation", "label": 2},
    {"premise": "I feel like we have a special connection.",
     "hypothesis": "sexually explicit or inappropriate content", "label": 2},
    {"premise": "If you really loved me you would do this.",
     "hypothesis": "building emotional trust with someone", "label": 1},
    {"premise": "Can you sneak out tonight?",
     "hypothesis": "asking about daily routine or when someone is alone", "label": 1},
]


# ---------------------------------------------------------------------------
# Fine-tuning logic
# ---------------------------------------------------------------------------

def prepare_dataset(samples: list, tokenizer, max_length: int = 128):
    """Convert NLI samples into a HuggingFace Dataset for training."""
    from datasets import Dataset

    premises = [s["premise"] for s in samples]
    hypotheses = [s["hypothesis"] for s in samples]
    labels = [s["label"] for s in samples]

    encodings = tokenizer(
        premises,
        hypotheses,
        truncation=True,
        padding="max_length",
        max_length=max_length,
        return_tensors="pt",
    )

    dataset = Dataset.from_dict({
        "input_ids": encodings["input_ids"],
        "attention_mask": encodings["attention_mask"],
        "labels": labels,
    })
    dataset.set_format("torch")
    return dataset


def finetune(
    output_dir: str = None,
    dataset_path: str = None,
    epochs: int = 4,
    batch_size: int = 16,
    learning_rate: float = 2e-5,
    warmup_ratio: float = 0.1,
    weight_decay: float = 0.01,
    max_length: int = 128,
    base_model: str = "typeform/distilbert-base-uncased-mnli",
):
    """
    Fine-tune the NLI model on grooming-specific data.

    Uses the built-in GROOMING_NLI_SAMPLES by default, or loads from
    a JSON file if dataset_path is provided.
    """
    try:
        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification,
            TrainingArguments,
            Trainer,
        )
        import torch
    except ImportError:
        logger.error(
            "Required packages not installed. Run:\n"
            "  pip install transformers[torch] datasets accelerate"
        )
        sys.exit(1)

    output_dir = output_dir or str(DEFAULT_OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    # Load training data
    if dataset_path and os.path.exists(dataset_path):
        logger.info(f"Loading custom dataset from {dataset_path}")
        with open(dataset_path, "r", encoding="utf-8") as f:
            samples = json.load(f)
        logger.info(f"Loaded {len(samples)} samples from file.")
    else:
        samples = GROOMING_NLI_SAMPLES
        logger.info(f"Using built-in grooming NLI dataset ({len(samples)} samples).")

    # Load base model and tokenizer
    logger.info(f"Loading base model: {base_model}")
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        base_model,
        num_labels=3,  # entailment, neutral, contradiction
    )

    # Prepare dataset
    logger.info("Tokenizing dataset...")
    train_dataset = prepare_dataset(samples, tokenizer, max_length)

    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        learning_rate=learning_rate,
        warmup_ratio=warmup_ratio,
        weight_decay=weight_decay,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        fp16=torch.cuda.is_available(),
        report_to="none",
        seed=42,
        dataloader_pin_memory=False,
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
    )

    # Train
    logger.info(f"Starting fine-tuning for {epochs} epochs...")
    logger.info(f"  Batch size: {batch_size}")
    logger.info(f"  Learning rate: {learning_rate}")
    logger.info(f"  Output: {output_dir}")
    trainer.train()

    # Save final model
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    logger.info(f"\nFine-tuned model saved to: {output_dir}")
    logger.info(
        "\nTo use the fine-tuned model, add to your .env:\n"
        f"  FINETUNED_MODEL_PATH={os.path.relpath(output_dir, BASE_DIR)}"
    )

    return output_dir


# ---------------------------------------------------------------------------
# Export dataset for external annotation
# ---------------------------------------------------------------------------

def export_dataset(output_path: str = None):
    """Export the built-in dataset to JSON for review or augmentation."""
    output_path = output_path or str(DEFAULT_DATASET_PATH)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(GROOMING_NLI_SAMPLES, f, indent=2, ensure_ascii=False)
    logger.info(f"Dataset exported to: {output_path} ({len(GROOMING_NLI_SAMPLES)} samples)")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune DistilBERT-MNLI on grooming-specific NLI data"
    )
    parser.add_argument("--epochs", type=int, default=4, help="Training epochs (default: 4)")
    parser.add_argument("--lr", type=float, default=2e-5, help="Learning rate (default: 2e-5)")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size (default: 16)")
    parser.add_argument("--max-length", type=int, default=128, help="Max token length (default: 128)")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for model")
    parser.add_argument("--dataset", type=str, default=None, help="Path to custom NLI dataset JSON")
    parser.add_argument("--base-model", type=str, default="typeform/distilbert-base-uncased-mnli",
                        help="Base model to fine-tune")
    parser.add_argument("--export-dataset", action="store_true",
                        help="Export built-in dataset to JSON and exit")

    args = parser.parse_args()

    if args.export_dataset:
        export_dataset()
        return

    finetune(
        output_dir=args.output_dir,
        dataset_path=args.dataset,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        max_length=args.max_length,
        base_model=args.base_model,
    )


if __name__ == "__main__":
    main()
