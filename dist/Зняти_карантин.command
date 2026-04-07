#!/bin/bash
echo "🔒 Знімаю карантин з VideoForge..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/VideoForge.app" ]; then
    xattr -cr "$SCRIPT_DIR/VideoForge.app" 2>/dev/null
    echo "✅ Готово! Відкриваю VideoForge..."
    open "$SCRIPT_DIR/VideoForge.app"
elif [ -d "/Applications/VideoForge.app" ]; then
    xattr -cr "/Applications/VideoForge.app" 2>/dev/null
    echo "✅ Готово! Відкриваю VideoForge..."
    open "/Applications/VideoForge.app"
else
    echo "❌ VideoForge.app не знайдено. Покладіть цей скрипт поруч з .app"
fi
read -p "Натисніть Enter щоб закрити..."
