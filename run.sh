#!/bin/bash

MODEL_NAME="glm-4-flash-250414"

python main.py \
    --map_name Flat32 \
    --difficulty VeryEasy \
    --model $MODEL_NAME \
    --ai_build RandomBuild \
    --player_name sc2agent \
    --enable_plan \
    --enable_plan_verifier \
    --enable_action_verifier
