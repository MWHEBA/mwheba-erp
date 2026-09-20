@echo off
chcp 65001 >nul
title تثبيت MariaDB كخدمة أساسية في ويندوز (Windows Service)

echo ============================================================
echo   تثبيت MariaDB كخدمة أساسية تعمل تلقائياً مع تشغيل الويندوز
echo ============================================================
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] تنبيه: يجب تشغيل هذا الملف كمسؤول (Run as Administrator).
    echo.
    echo اضغط كليك يمين على الملف واختر "Run as administrator"
    echo.
    pause
    exit /b 1
)

set "MARIADB_EXE=C:\Users\UTD\mariadb-10.11\bin\mysqld.exe"
set "MARIADB_INI=C:\Users\UTD\mariadb-10.11\data\my.ini"

if not exist "%MARIADB_EXE%" (
    echo [X] لم يتم العثور على MariaDB في المسار المحدد:
    echo %MARIADB_EXE%
    pause
    exit /b 1
)

echo [*] إيقاف وحذف أي خدمات قديمة متعارضة (مثل XAMPP)...
sc stop mysql >nul 2>&1
sc delete mysql >nul 2>&1

sc stop MariaDB >nul 2>&1
sc delete MariaDB >nul 2>&1

echo [*] تسجيل MariaDB كخدمة نظام تلقائية (Auto Start)...
"%MARIADB_EXE%" --install MariaDB --defaults-file="%MARIADB_INI%"

echo [*] تشغيل خدمة MariaDB...
net start MariaDB

echo.
echo ============================================================
echo [OK] تم التثبيت والتشغيل بنجاح!
echo ستعمل قاعدة البيانات الآن في الخلفية تلقائياً مع فتح الجهاز.
echo ============================================================
pause
