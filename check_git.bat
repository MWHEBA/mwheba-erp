@echo off
chcp 65001 > nul
echo.
echo ======================================================================
echo  MWHEBA ERP - فحص أخطاء وأسرار ومشاكل Git والمشروع
echo ======================================================================
python "%~dp0scripts\check_git_issues.py" %*
echo.
pause
