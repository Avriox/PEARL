---
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- dense
base_model: Salesforce/codet5p-220m-py
pipeline_tag: sentence-similarity
library_name: sentence-transformers
metrics:
- cosine_accuracy
- cosine_accuracy_threshold
- cosine_f1
- cosine_f1_threshold
- cosine_precision
- cosine_recall
- cosine_ap
- cosine_mcc
model-index:
- name: SentenceTransformer based on Salesforce/codet5p-220m-py
  results:
  - task:
      type: binary-classification
      name: Binary Classification
    dataset:
      name: ft eval bin small
      type: ft_eval_bin_small
    metrics:
    - type: cosine_accuracy
      value: 0.6663333333333333
      name: Cosine Accuracy
    - type: cosine_accuracy_threshold
      value: 0.9999982714653015
      name: Cosine Accuracy Threshold
    - type: cosine_f1
      value: 0.5008809463881198
      name: Cosine F1
    - type: cosine_f1_threshold
      value: 0.9630452394485474
      name: Cosine F1 Threshold
    - type: cosine_precision
      value: 0.3346787756474941
      name: Cosine Precision
    - type: cosine_recall
      value: 0.995
      name: Cosine Recall
    - type: cosine_ap
      value: 0.29403122491336825
      name: Cosine Ap
    - type: cosine_mcc
      value: 0.02994931623215885
      name: Cosine Mcc
---

# SentenceTransformer based on Salesforce/codet5p-220m-py

This is a [sentence-transformers](https://www.SBERT.net) model finetuned from [Salesforce/codet5p-220m-py](https://huggingface.co/Salesforce/codet5p-220m-py). It maps sentences & paragraphs to a 768-dimensional dense vector space and can be used for semantic textual similarity, semantic search, paraphrase mining, text classification, clustering, and more.

## Model Details

### Model Description
- **Model Type:** Sentence Transformer
- **Base model:** [Salesforce/codet5p-220m-py](https://huggingface.co/Salesforce/codet5p-220m-py) <!-- at revision 8844b8a8b0600ffce926b71880003f8b21dfd5e6 -->
- **Maximum Sequence Length:** 512 tokens
- **Output Dimensionality:** 768 dimensions
- **Similarity Function:** Cosine Similarity
<!-- - **Training Dataset:** Unknown -->
<!-- - **Language:** Unknown -->
<!-- - **License:** Unknown -->

### Model Sources

- **Documentation:** [Sentence Transformers Documentation](https://sbert.net)
- **Repository:** [Sentence Transformers on GitHub](https://github.com/UKPLab/sentence-transformers)
- **Hugging Face:** [Sentence Transformers on Hugging Face](https://huggingface.co/models?library=sentence-transformers)

### Full Model Architecture

```
SentenceTransformer(
  (0): Transformer({'max_seq_length': 512, 'do_lower_case': False, 'architecture': 'PeftModelForFeatureExtraction'})
  (1): Pooling({'word_embedding_dimension': 768, 'pooling_mode_cls_token': False, 'pooling_mode_mean_tokens': True, 'pooling_mode_max_tokens': False, 'pooling_mode_mean_sqrt_len_tokens': False, 'pooling_mode_weightedmean_tokens': False, 'pooling_mode_lasttoken': False, 'include_prompt': True})
)
```

## Usage

### Direct Usage (Sentence Transformers)

First install the Sentence Transformers library:

```bash
pip install -U sentence-transformers
```

Then you can load this model and run inference.
```python
from sentence_transformers import SentenceTransformer

# Download from the 🤗 Hub
model = SentenceTransformer("sentence_transformers_model_id")
# Run inference
sentences = [
    'The weather is lovely today.',
    "It's so sunny outside!",
    'He drove to the stadium.',
]
embeddings = model.encode(sentences)
print(embeddings.shape)
# [3, 768]

# Get the similarity scores for the embeddings
similarities = model.similarity(embeddings, embeddings)
print(similarities)
# tensor([[1.0000, 0.8875, 0.8780],
#         [0.8875, 1.0000, 0.8851],
#         [0.8780, 0.8851, 1.0000]])
```

<!--
### Direct Usage (Transformers)

<details><summary>Click to see the direct usage in Transformers</summary>

</details>
-->

<!--
### Downstream Usage (Sentence Transformers)

You can finetune this model on your own dataset.

<details><summary>Click to expand</summary>

</details>
-->

<!--
### Out-of-Scope Use

*List how the model may foreseeably be misused and address what users ought not to do with the model.*
-->

## Evaluation

### Metrics

#### Binary Classification

* Dataset: `ft_eval_bin_small`
* Evaluated with [<code>BinaryClassificationEvaluator</code>](https://sbert.net/docs/package_reference/sentence_transformer/evaluation.html#sentence_transformers.evaluation.BinaryClassificationEvaluator)

| Metric                    | Value     |
|:--------------------------|:----------|
| cosine_accuracy           | 0.6663    |
| cosine_accuracy_threshold | 1.0       |
| cosine_f1                 | 0.5009    |
| cosine_f1_threshold       | 0.963     |
| cosine_precision          | 0.3347    |
| cosine_recall             | 0.995     |
| **cosine_ap**             | **0.294** |
| cosine_mcc                | 0.0299    |

<!--
## Bias, Risks and Limitations

*What are the known or foreseeable issues stemming from this model? You could also flag here known failure cases or weaknesses of the model.*
-->

<!--
### Recommendations

*What are recommendations with respect to the foreseeable issues? For example, filtering explicit content.*
-->

## Training Details

### Training Logs
| Epoch | Step | ft_eval_bin_small_cosine_ap |
|:-----:|:----:|:---------------------------:|
| -1    | -1   | 0.2940                      |


### Framework Versions
- Python: 3.13.7
- Sentence Transformers: 5.1.0
- Transformers: 4.56.2
- PyTorch: 2.8.0+cu128
- Accelerate: 1.10.1
- Datasets: 4.1.1
- Tokenizers: 0.22.1

## Citation

### BibTeX

<!--
## Glossary

*Clearly define terms in order to be accessible across audiences.*
-->

<!--
## Model Card Authors

*Lists the people who create the model card, providing recognition and accountability for the detailed work that goes into its construction.*
-->

<!--
## Model Card Contact

*Provides a way for people who have updates to the Model Card, suggestions, or questions, to contact the Model Card authors.*
-->