@echo off
setlocal enabledelayedexpansion

set n=100  :: Replace 10 with the number of times you want to run the command

for /l %%i in (1,1,%n%) do (
    echo Running iteration %%i
    python main.py Flat32
)

endlocal