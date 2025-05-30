#!/bin/bash

echo "📦 Starting push to GitHub..."

set -e  # Stop script on error

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "❌ Git is not installed."
    exit 1
fi

# Add all changes
git add .

# Prompt for commit message
default_msg="🔁 Sync local changes to GitHub ($(date '+%Y-%m-%d %H:%M:%S'))"
echo "💬 Enter commit message (leave blank for default):"
read commit_msg

# Use default message if none provided
if [ -z "$commit_msg" ]; then
    commit_msg=$default_msg
fi

# Commit and push
git commit -m "$commit_msg"
git push origin main

echo "✅ Changes pushed to GitHub successfully."
