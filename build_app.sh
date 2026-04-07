#!/bin/bash
# VideoForge — Simple macOS App Builder v3
# Usage: bash build_app.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
DIST="$DIR/dist"
APP="$DIST/VideoForge.app"
C="$APP/Contents"

# Find Python version from venv
PYVER="3.14"
SITE="$DIR/venv/lib/python${PYVER}/site-packages"

if [ ! -d "$SITE" ]; then
    echo "❌ venv/lib/python${PYVER}/site-packages not found"
    exit 1
fi

echo "🎬 Building VideoForge.app..."

# Clean
rm -rf "$APP"
mkdir -p "$C/MacOS" "$C/Resources/app" "$C/Resources/site-packages"

# Copy app source
echo "  📝 Copying source..."
cp "$DIR/gui.py" "$DIR/config.py" "$DIR/videoforge.py" \
   "$DIR/scene_splitter.py" "$DIR/subtitle_gen.py" \
   "$DIR/visual_finder.py" "$DIR/video_assembler.py" \
   "$C/Resources/app/"
cp "$DIR/.env.example" "$C/Resources/app/"
[ -f "$DIR/.env" ] && cp "$DIR/.env" "$C/Resources/app/"
[ -d "$DIR/assets" ] && cp -R "$DIR/assets" "$C/Resources/app/"

# Copy site-packages (skip dev tools and caches)
echo "  📦 Copying packages... (this takes ~10 seconds)"
rsync -a \
    --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='pip' --exclude='pip-*' \
    --exclude='setuptools' --exclude='setuptools-*' \
    --exclude='pkg_resources' --exclude='_distutils_hack' \
    "$SITE/" "$C/Resources/site-packages/"

# Compile C launcher
echo "  🔨 Compiling launcher..."
cat > "$DIST/_tmp.c" << 'ENDOFC'
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <mach-o/dyld.h>

int main(int argc, char *argv[]) {
    char exe[4096]; uint32_t sz = sizeof(exe);
    if (_NSGetExecutablePath(exe, &sz)) return 1;
    char rp[4096];
    if (!realpath(exe, rp)) return 1;

    /* Go from .../Contents/MacOS/VideoForge to .../Contents */
    char *s = strrchr(rp, '/'); if (!s) return 1; *s = 0;
    s = strrchr(rp, '/'); if (!s) return 1; *s = 0;

    char res[4096], app[4096], sp[4096], flag[4096];
    snprintf(res, 4096, "%s/Resources", rp);
    snprintf(app, 4096, "%s/Resources/app", rp);
    snprintf(sp,  4096, "%s/Resources/site-packages", rp);
    snprintf(flag,4096, "%s/Resources/.qclear", rp);

    /* Quarantine removal — first run only */
    struct stat st;
    if (stat(flag, &st) != 0) {
        char cmd[8192];
        snprintf(cmd, 8192, "xattr -cr '%s/..' 2>/dev/null; xattr -cr '%s' 2>/dev/null", rp, sp);
        system(cmd);
        FILE *f = fopen(flag, "w");
        if (f) { fputs("1", f); fclose(f); }
    }

    /* Find python3 */
    const char *py[] = {
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
        NULL
    };
    const char *python = NULL;
    for (int i = 0; py[i]; i++) {
        if (access(py[i], X_OK) == 0) { python = py[i]; break; }
    }
    if (!python) {
        system("osascript -e 'display alert \"Python 3 not found\" message \"Install Python 3 via brew or python.org\" as critical'");
        return 1;
    }

    /* Environment */
    char pp[8192];
    snprintf(pp, 8192, "%s:%s", sp, app);
    setenv("PYTHONPATH", pp, 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);

    char *home = getenv("HOME");
    if (home) {
        char od[4096], cd[4096], ce[4096], ae[4096];
        snprintf(od, 4096, "%s/Desktop/VideoForge_Output", home);
        setenv("VIDEOFORGE_OUTPUT_DIR", od, 1);
        mkdir(od, 0755);
        snprintf(cd, 4096, "%s/Library/Application Support/VideoForge", home);
        setenv("VIDEOFORGE_CONFIG_DIR", cd, 1);
        mkdir(cd, 0755);
        snprintf(ce, 4096, "%s/.env", cd);
        snprintf(ae, 4096, "%s/.env", app);
        if (stat(ce, &st) != 0 && stat(ae, &st) == 0) {
            char cp[8192];
            snprintf(cp, 8192, "cp '%s' '%s'", ae, ce);
            system(cp);
        }
    }

    /* Add imageio_ffmpeg to PATH */
    char fd[4096], np[16384];
    snprintf(fd, 4096, "%s/imageio_ffmpeg/binaries", sp);
    char *op = getenv("PATH");
    snprintf(np, 16384, "%s:%s", fd, op ? op : "/usr/bin");
    setenv("PATH", np, 1);

    /* Symlink ffmpeg if needed */
    char fl[4096];
    snprintf(fl, 4096, "%s/ffmpeg", fd);
    if (stat(fl, &st) != 0) {
        char lc[8192];
        snprintf(lc, 8192, "cd '%s' && for f in ffmpeg-*; do [ -f \"$f\" ] && ln -sf \"$f\" ffmpeg; break; done 2>/dev/null", fd);
        system(lc);
    }

    chdir(app);
    execl(python, "python3", "-u", "gui.py", NULL);
    perror("exec");
    return 1;
}
ENDOFC

clang -O2 -arch arm64 -o "$C/MacOS/VideoForge" "$DIST/_tmp.c"
rm "$DIST/_tmp.c"
chmod +x "$C/MacOS/VideoForge"

# Info.plist
echo "  📋 Creating Info.plist..."
cat > "$C/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>VideoForge</string>
<key>CFBundleDisplayName</key><string>VideoForge</string>
<key>CFBundleIdentifier</key><string>com.videoforge.app</string>
<key>CFBundleVersion</key><string>1.0</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleExecutable</key><string>VideoForge</string>
<key>LSMinimumSystemVersion</key><string>12.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>LSApplicationCategoryType</key><string>public.app-category.video</string>
</dict></plist>
PLIST

# Strip quarantine
echo "  🔒 Stripping quarantine..."
xattr -cr "$APP" 2>/dev/null || true

echo ""
echo "✅ Done! $(du -sh "$APP" | cut -f1)"
echo "   open dist/VideoForge.app"
