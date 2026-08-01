@echo off
cd /d "%~dp0"
py -c "print('hb_lines=' + str(len(open('hourly_briefing.py',encoding='utf-8').read().splitlines())))" > hb_check.txt 2>&1
py -c "import ast; ast.parse(open('hourly_briefing.py',encoding='utf-8').read()); print('hb_syntax=OK')" >> hb_check.txt 2>&1
py -c "import ast; ast.parse(open('engine/news_guard.py',encoding='utf-8').read()); print('news_guard=OK')" >> hb_check.txt 2>&1
echo done>> hb_check.txt
