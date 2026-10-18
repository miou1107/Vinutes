#!/bin/bash
# Install or update Vinutes, the menu-bar meeting recorder. Mac with Apple silicon only.
#
#   recorder/install.sh        safe to run again; run it after every update to rebuild the app
#
# What it does, in order:
#   1. checks the Mac (Apple silicon, Xcode command line tools for swiftc, Python 3.10+)
#   2. makes a Python environment in $MINUTES_HOME/venv with the transcriber (mlx-whisper, OpenCC) and the
#      packages the scripts use (python-docx, markdown-it-py, google-auth-oauthlib)
#   3. downloads the speech model once (whisper-large-v3-turbo, about 1.6 GB, into ~/.cache/huggingface) and the
#      voice model that tells the speakers apart (3D-Speaker CAM++, about 28 MB, into $MINUTES_HOME/models)
#   4. builds ~/Applications/Vinutes.app from MeetingRecorder.swift and the meeting window's page (recorder/app),
#      signs it for this Mac only, and starts it.
#      Skipped when the sources did not change: every new build is a new app to macOS, which asks for the
#      microphone again.
#   5. writes $MINUTES_HOME/recorder.json so the app knows where Python and these scripts are, and, once, keeps
#      Chinese for people who used Vinutes before it spoke English ("language": "zh-TW" in settings.json)
#   6. connects Vinutes to the AI tools on this Mac, so they can look things up in the meetings
#      (scripts/connect_agents.py)
#   7. when the app was installed or updated (not when nothing changed), downloads one small file from the
#      counter on GitHub (install.txt or update.txt), so its download count shows roughly how many Macs use
#      Vinutes. Nothing about the Mac or its user is sent. VINUTES_NO_COUNT=1, or a file named no-count in
#      $MINUTES_HOME (which the update button's run also sees), skips it.
# One AI CLI must be installed and signed in (Claude Code, Codex or Antigravity); the script says so when none is.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# the same folder the vin-meeting-minutes-zh skill uses: both share one Google sign-in and the user's settings
MINUTES_HOME="${MINUTES_HOME:-$HOME/.config/vin-meeting-minutes-zh}"
APP="$HOME/Applications/Vinutes.app"
# names used before: 會議錄音 until 2026-10-14, Vin 會議記錄助手 until Vinutes moved to its own repo (2026-10-15)
OLD_APPS=("$HOME/Applications/會議錄音.app" "$HOME/Applications/Vin 會議記錄助手.app")
BUNDLE_ID="com.github.miou1107.vinutes"
OLD_BUNDLE_ID="com.github.miou1107.meeting-recorder"
step() { printf '\n== %s\n' "$*"; }

# macOS remembers the microphone and the Mac's-sound permission for the app's signature. Signed ad hoc, every build
# is a new signature and asks again; signed with one certificate kept in the login keychain, updates keep the
# permission. The certificate is made here the first time (self-signed, for signing code only, never leaves the Mac).
# Prints the certificate's hash, or nothing when it could not be made.
SIGN_NAME="Vinutes Local Signing"
find_identity() {
  security find-identity -p codesigning "$HOME/Library/Keychains/login.keychain-db" 2>/dev/null \
    | awk -v n="\"$SIGN_NAME\"" 'index($0, n) { print $2; exit }'
}
signing_identity() {
  local hash dir
  hash="$(find_identity)"
  if [[ -z "$hash" ]]; then
    dir="$(mktemp -d)"
    printf '%s\n' '[req]' 'distinguished_name=dn' 'prompt=no' 'x509_extensions=ext' '[dn]' "CN=$SIGN_NAME" \
      '[ext]' 'basicConstraints=critical,CA:false' 'keyUsage=critical,digitalSignature' \
      'extendedKeyUsage=critical,codeSigning' > "$dir/cert.conf"
    /usr/bin/openssl req -x509 -newkey rsa:2048 -nodes -days 7300 -config "$dir/cert.conf" \
        -keyout "$dir/key.pem" -out "$dir/cert.pem" >/dev/null 2>&1 \
      && /usr/bin/openssl pkcs12 -export -inkey "$dir/key.pem" -in "$dir/cert.pem" -out "$dir/id.p12" \
        -passout pass:vinutes >/dev/null 2>&1 \
      && security import "$dir/id.p12" -k "$HOME/Library/Keychains/login.keychain-db" -P vinutes -x \
        -T /usr/bin/codesign >/dev/null 2>&1
    rm -rf "$dir"
    hash="$(find_identity)"
  fi
  [[ -n "$hash" ]] && echo "$hash"
}

step "Checking this Mac"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo "NOT SUPPORTED: the recorder needs a Mac with Apple silicon (M1 or newer)."; exit 1
fi
if ! xcrun --find swiftc >/dev/null 2>&1; then
  echo "NEED XCODE TOOLS: run  xcode-select --install , press Install in the window that opens, then run this again."; exit 1
fi
PY=""
for p in /opt/homebrew/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
         /usr/local/bin/python3 /usr/bin/python3; do
  if [[ -x "$p" ]] && "$p" -c 'import sys, platform; sys.exit(sys.version_info < (3, 10) or platform.machine() != "arm64")' 2>/dev/null; then
    PY="$p"; break
  fi
done
[[ -n "$PY" ]] || { echo "NEED PYTHON: install Python 3.10 or newer for Apple silicon (python.org or Homebrew)."; exit 1; }
echo "python: $PY"

step "Python packages (in $MINUTES_HOME/venv)"
mkdir -p "$MINUTES_HOME"; chmod 700 "$MINUTES_HOME"
[[ -x "$MINUTES_HOME/venv/bin/python" ]] || "$PY" -m venv "$MINUTES_HOME/venv"
VPY="$MINUTES_HOME/venv/bin/python"
"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet mlx-whisper opencc-python-reimplemented python-docx markdown-it-py google-auth-oauthlib \
  sherpa-onnx soundfile numpy
echo "ok"

step "Speech model (about 1.6 GB, downloaded once)"
"$VPY" -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/whisper-large-v3-turbo')" >/dev/null
echo "ok"

step "Voice model for telling the speakers apart (about 28 MB, downloaded once)"
mkdir -p "$MINUTES_HOME/models"
VOICE_MODEL="$MINUTES_HOME/models/campplus.onnx"
if [[ -s "$VOICE_MODEL" ]]; then
  echo "ok"
elif curl -fsSL -o "$VOICE_MODEL.part" \
     "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"; then
  mv "$VOICE_MODEL.part" "$VOICE_MODEL"; echo "ok"
else
  rm -f "$VOICE_MODEL.part"
  echo "(not downloaded: transcripts still work, without who said each line; run this again later)"
fi

step "AI that writes the minutes (Claude Code, Codex or Antigravity)"
FOUND=""
for cli in claude codex agy; do
  if WHERE="$(/bin/zsh -lc "command -v $cli" 2>/dev/null)" && [[ -n "$WHERE" ]]; then echo "$cli: $WHERE"; FOUND=1; fi
done
if [[ -z "$FOUND" ]]; then
  echo "MISSING: the recorder needs one of them to write the minutes: Claude Code (claude), Codex (codex) or"
  echo "Antigravity (agy). Install one and sign in; the app's Setup Checklist picks which one it uses."
fi

step "Building $APP"
make_icon() {
  swift "$ROOT/recorder/make_icon.swift" "$BUILD/icon.png" 2>/dev/null || return 1
  for px in 16 32 128 256 512; do
    sips -z $px $px "$BUILD/icon.png" --out "$BUILD/AppIcon.iconset/icon_${px}x${px}.png" >/dev/null || return 1
    sips -z $((px * 2)) $((px * 2)) "$BUILD/icon.png" --out "$BUILD/AppIcon.iconset/icon_${px}x${px}@2x.png" >/dev/null || return 1
  done
  iconutil -c icns "$BUILD/AppIcon.iconset" -o "$NEW/Contents/Resources/AppIcon.icns"
}
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION" 2>/dev/null || true)"
SIGN_ID="$(signing_identity || true)"
SOURCE_SUM="$(cat "$ROOT/recorder/MeetingRecorder.swift" "$ROOT/recorder/Capture.swift" "$ROOT/recorder/MenuPanel.swift" "$ROOT/recorder/Captions.swift" "$ROOT/recorder/Info.plist" \
              "$ROOT/recorder/make_icon.swift" "$ROOT"/recorder/app/* \
              "$ROOT"/recorder/l10n/*.lproj/* | shasum -a 256 | cut -c1-16)-${VERSION:-0}-${SIGN_ID:0:8}"   # a new certificate signs again
if [[ -x "$APP/Contents/MacOS/MeetingRecorder" && "$(cat "$APP/Contents/Resources/source.sum" 2>/dev/null)" == "$SOURCE_SUM" ]]; then
  echo "unchanged (version ${VERSION:-unknown})"
else
  BUILD="$(mktemp -d)"
  trap 'rm -rf "$BUILD"' EXIT
  # build first, so a failed build leaves the running app alone
  # with two files, the one with the app's top-level code has to be called main.swift
  cp "$ROOT/recorder/MeetingRecorder.swift" "$BUILD/main.swift"
  swiftc -O -swift-version 5 -o "$BUILD/MeetingRecorder" "$BUILD/main.swift" "$ROOT/recorder/Capture.swift" "$ROOT/recorder/MenuPanel.swift"
  # live captions run in a helper of their own; it needs macOS 26, so on an older Mac the app is built without it
  swiftc -O -swift-version 5 -parse-as-library -o "$BUILD/VinutesCaptions" "$ROOT/recorder/Captions.swift" 2>/dev/null \
    || echo "(no live captions: they need macOS 26 or later)"
  NEW="$BUILD/Vinutes.app"
  mkdir -p "$NEW/Contents/MacOS" "$NEW/Contents/Resources" "$BUILD/AppIcon.iconset"
  cp "$BUILD/MeetingRecorder" "$NEW/Contents/MacOS/MeetingRecorder"
  [[ -x "$BUILD/VinutesCaptions" ]] && cp "$BUILD/VinutesCaptions" "$NEW/Contents/MacOS/VinutesCaptions"
  cp -R "$ROOT/recorder/app" "$NEW/Contents/Resources/app"
  # the microphone question in English or Chinese, whichever the Mac uses (en.lproj, zh-Hant.lproj)
  cp -R "$ROOT"/recorder/l10n/*.lproj "$NEW/Contents/Resources/"
  sed "s/__VERSION__/${VERSION:-0}/g" "$ROOT/recorder/Info.plist" > "$NEW/Contents/Info.plist"
  make_icon || echo "(no icon: drawing it failed; the app works without one)"
  echo "$SOURCE_SUM" > "$NEW/Contents/Resources/source.sum"
  if [[ -n "$SIGN_ID" ]] && codesign --force --timestamp=none --sign "$SIGN_ID" "$NEW" >/dev/null 2>&1; then
    :
  else
    echo "(signed without the Vinutes certificate: after this update macOS asks again for the microphone and the Mac's sound)"
    codesign --force --sign - "$NEW" >/dev/null || { echo "STOP: signing the app failed (codesign)."; exit 1; }
  fi

  if pgrep -xq MeetingRecorder; then
    # quitting asks the user first when a recording is running
    for id in "$BUNDLE_ID" "$OLD_BUNDLE_ID"; do
      osascript -e 'with timeout of 20 seconds' -e "tell application id \"$id\" to quit" -e 'end timeout' >/dev/null 2>&1 || true
    done
    for _ in $(seq 20); do pgrep -xq MeetingRecorder || break; sleep 1; done
    if pgrep -xq MeetingRecorder; then
      echo "STOP: Vinutes is still running (a recording or a window may be open). Quit it from its menu, then run this again."
      exit 1
    fi
  fi
  COUNT=install                              # what the counter at the end records
  for old in "$APP" "${OLD_APPS[@]}"; do if [[ -d "$old" ]]; then COUNT=update; fi; done
  rm -rf "$APP" "${OLD_APPS[@]}"
  mkdir -p "$(dirname "$APP")"
  mv "$NEW" "$APP"
  echo "ok (version ${VERSION:-unknown})"
fi

step "Settings"
"$VPY" - "$MINUTES_HOME/recorder.json" "$VPY" "$ROOT" "$MINUTES_HOME" <<'EOF'
import json, os, sys
path, python, root, home = sys.argv[1:5]
open(path, 'w').write(json.dumps({'python': python, 'app_dir': root}, indent=2))

# Vinutes was Chinese only until it learned English. Someone who already has recordings keeps Chinese; a new
# install writes nothing and follows the Mac's language. Checked once (the marker), so a later run of this script
# never switches a new user who has started recording to Chinese.
marker = os.path.join(home, 'language-checked')
settings = os.path.join(home, 'settings.json')
if not os.path.exists(marker):
    if os.path.isdir(os.path.join(home, 'recordings')):
        data = {}
        if os.path.exists(settings):
            try:
                data = json.load(open(settings, encoding='utf-8'))
            except (OSError, ValueError):
                data = None                       # a file we cannot read is left alone
        if isinstance(data, dict) and 'language' not in data:
            data['language'] = 'zh-TW'
            # writing over the file keeps its permissions (600 stays 600)
            with open(settings, 'w', encoding='utf-8') as f:
                f.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
            print('kept Chinese for this existing install')
    open(marker, 'w').close()
EOF
chmod 600 "$MINUTES_HOME/recorder.json"
echo "ok"

# the AI tools on this Mac (Claude Code, Codex, Gemini, Claude's app, Antigravity, Cursor) can look things up in
# the meetings, and change them when asked (scripts/mcp_server.py)
echo "connecting Vinutes to the AI tools on this Mac:"
"$VPY" "$ROOT/scripts/connect_agents.py" | sed 's/^/  /' || echo "  (not connected; run scripts/connect_agents.py later)"

open "$APP"

# one download from the counter on GitHub per install or update; quiet, and never stops the install
if [[ -n "${COUNT:-}" && -z "${VINUTES_NO_COUNT:-}" && ! -e "$MINUTES_HOME/no-count" ]]; then
  curl -fsSL --max-time 5 -o /dev/null "https://github.com/miou1107/Vinutes/releases/download/counter/$COUNT.txt" || true
fi
echo
echo "DONE: Vinutes is in the menu bar (the microphone icon at the top right of the screen)."
echo "The first recording asks for microphone permission; the first finished job asks to show notifications."
