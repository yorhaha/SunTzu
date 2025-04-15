# SC2Arena

A StarCraft II benchmark for LLMs!

## Setup

Only tested on Windows python 3.9.

1. Install StarCraft II: https://starcraft2.blizzard.com/. (Optional) Change language to be English.
2. Download maps from https://github.com/Blizzard/s2client-proto?tab=readme-ov-file#map-packs (Melee is required) and install them.
3. Clone repo and setup python environment: `pip install -r requirements.txt`
4. Setup python-sc2: https://github.com/BurnySc2/python-sc2?tab=readme-ov-file#starcraft-ii

```
pip install --upgrade --force-reinstall https://github.com/BurnySc2/python-sc2/archive/develop.zip
```

5. Setup `.env` file as `.env_template`.
6. Choose player from `main.py`. Setup `llm_config`.

## Run

```
python main.py ^
--map_name Flat32 ^
--difficulty Easy ^
--model Qwen2.5-32B-Instruct ^
--ai_build RandomBuild ^
--enable_rag ^
--enable_plan_verifier ^
--enable_action_verifier
```

## GUI

```
pip install streamlit

streamlit run gui.py
```