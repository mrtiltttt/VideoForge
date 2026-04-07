#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  VideoForge — Зняття карантину
#  Подвійний клік на цей файл, щоб зняти блокування macOS
# ═══════════════════════════════════════════════════════════════

echo ""
echo "🔒 Знімаю карантин з VideoForge..."
echo ""

# Find VideoForge.app relative to this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -d "$SCRIPT_DIR/VideoForge.app" ]; then
    APP="$SCRIPT_DIR/VideoForge.app"
elif [ -d "/Applications/VideoForge.app" ]; then
    APP="/Applications/VideoForge.app"
else
    echo "❌ VideoForge.app не знайдено."
    echo "   Перемісти цей скрипт в ту ж папку де лежить VideoForge.app"
    echo ""
    read -p "Натисни Enter щоб закрити..."
    exit 1
fi

echo "  Знайдено: $APP"
echo "  Очищую атрибути безпеки..."
echo ""

xattr -cr "$APP" 2>/dev/null

echo "✅ Готово! Тепер можеш відкрити VideoForge.app"
echo ""

# Try to open it
open "$APP" 2>/dev/null

echo "Натисни Enter щоб закрити це вікно..."
read
