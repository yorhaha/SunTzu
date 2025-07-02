# SC2Arena

A StarCraft II battle arena for LLMs!

## Setup

Python 3.9+ is recommended.

1. Install StarCraft II: https://starcraft2.blizzard.com/. Optional: change language to be English.
2. Download maps from https://github.com/Blizzard/s2client-proto?tab=readme-ov-file#map-packs (Melee pack is required) and install them following the guide. The files are password protected with the password `iagreetotheeula`. 
3. Clone repo and setup python environment: `pip install -r requirements.txt`.
4. Setup python-sc2: https://github.com/BurnySc2/python-sc2?tab=readme-ov-file#starcraft-ii.

```
pip install --upgrade --force-reinstall https://github.com/BurnySc2/python-sc2/archive/develop.zip
```

5. Setup `.env` file as `.env_template`.

## Run

```
python main.py \
    --map_name Flat32 \
    --difficulty Hard \
    --model Qwen2.5-32B-Instruct \
    --ai_build RandomBuild \
    --enable_plan \
    --enable_plan_verifier \
    --enable_action_verifier
```

See `tools/constants.py` for detailed game settings.

## GUI

```
pip install streamlit

streamlit run gui.py
```

## References

- Tech tree:
  - https://osirissc2guide.com/starcraft-2-terran-structures.html
  - https://osirissc2guide.com/starcraft-2-protoss-structures.html
  - https://osirissc2guide.com/starcraft-2-zerg-structures.html