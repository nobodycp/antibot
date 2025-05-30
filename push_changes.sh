#!/bin/bash

echo "📦 بدء رفع التعديلات إلى GitHub..."

# إيقاف مؤقت لو فيه مشاكل
set -e

# اسم مجلد المشروع (اختياري فقط للعرض)
project_name="antibot"

# 1. تأكد من تواجد Git
if ! command -v git &> /dev/null; then
    echo "❌ Git غير مثبت."
    exit 1
fi

# 2. إضافة التعديلات
git add .

# 3. كتابة رسالة تلقائية أو مخصصة
default_msg="🔁 Sync local changes to GitHub ($(date '+%Y-%m-%d %H:%M:%S'))"
echo "💬 أدخل رسالة الالتزام (أو اضغط Enter لاستخدام الرسالة التلقائية):"
read commit_msg

if [ -z "$commit_msg" ]; then
    commit_msg=$default_msg
fi

git commit -m "$commit_msg"

# 4. رفع التعديلات
git push origin main

echo "✅ تم رفع التعديلات إلى GitHub بنجاح 🎉"
