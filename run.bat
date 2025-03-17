@echo off
setlocal enabledelayedexpansion

set n=1  :: Replace 10 with the number of times you want to run the command

for /l %%i in (1,1,%n%) do (
    echo Running iteration %%i
    python main.py ^
    --map Flat32 ^
    --difficulty Easy ^
    --model Qwen2.5-32B-Instruct ^
    --ai_build RandomBuild ^
    --enable_rag ^
    --enable_action_verifier
)

endlocal