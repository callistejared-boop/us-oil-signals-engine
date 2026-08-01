@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m py_compile engine\breaker_blocks.py engine\fibonacci.py engine\candlestick_patterns.py engine\chart_patterns.py engine\confluence.py > gap_test_output.txt 2>&1
echo COMPILE_DONE >> gap_test_output.txt
python -m pytest tests\ -q >> gap_test_output.txt 2>&1
echo TESTS_DONE >> gap_test_output.txt
python wti_note.py >> gap_test_output.txt 2>&1
echo LIVE_NOTE_DONE >> gap_test_output.txt
