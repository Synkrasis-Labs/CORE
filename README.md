# Running experiments (WiP)
The Week 1 FarmAgent-derived runtime is available in `function_calling/`.
See [the port guide](docs/FUNCTION_CALLING_PORT.md) for its interface and offline
tests. A scripted run of CORE's real Computations tools is available with
`python -m function_calling.computations_smoke`. It is not yet connected to the
existing CORE batch experiment runner described below.

This guide is for running the inference using our framework in order to generate a dataset of sequences of actions based on the provided dataset of prompts.

## Prerequisites
python>=3.10

## Instalation
```bash
git clone https://github.com/Bloodrock-AI/temp.git
```

```bash
pip install numpy torch transformers llm-tool accelerate
```
- More dependencies are needed based on the models that you are going to be using.

- We trust you to use the environment tools (uv, python-venv, conda) of your preference.

## Add your models
1. Add your model in the `ModeTypes` enum in `const.py`:
```python3
class ModelType(Enum):
    DEEPSCALE_R = "agentica-org/DeepScaleR-1.5B-Preview" # string is the same value as in hugging face
```
2. Add it to the experiment suite in `run_experiments.py`:
```python3
from const import ModelType
# ...

models = [
  ...
  ModelType.DEEPSCALE_R,
  ...
]
```

## Run the experiments
```bash
python3 run_experiments.py
```

This will produce 2 `json` files for each model.
1. `bfcl_results_<model_name>.json`: contains all the results (output sequences) from the BFCL-produced dataset.
2. `results_<model_name>.json`: contains all the results (output sequences) from our own dataset.

# List of models we could run
- Qwen 3 0.6B, 1.7B, 4B, 8B, 14B, 32B
- Llama 3.3 70B 
- Deepseek-qwen 7B, 14B
- Deepseek-llama 8B, 70B
