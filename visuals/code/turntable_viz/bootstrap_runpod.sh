#!/usr/bin/env bash
# Install Chrome/Node/ffmpeg + wire NVIDIA EGL/Vulkan so Chrome gets real WebGL2.
set -euo pipefail
log() { printf '[bootstrap] %s\n' "$*"; }
if ! command -v nvidia-smi >/dev/null; then
  echo "FATAL: nvidia-smi missing; refusing to render on a non-GPU box" >&2; exit 2
fi
nvidia-smi -L || true
export DEBIAN_FRONTEND=noninteractive
export NVIDIA_DRIVER_CAPABILITIES="${NVIDIA_DRIVER_CAPABILITIES:-compute,utility,graphics,display,video}"
export NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-all}"

run_to() {
  local t=$1; shift
  log "$* (timeout ${t}s)"
  timeout --foreground -k 15 "$t" "$@"
}

# Base images ship a deadsnakes PPA we never use; when launchpad is down (Mix 08 r7: 503s) every
# apt-get update, including the one inside the nodesource setup script, stalls until our timeout.
# Drop third-party PPAs and bound apt's own network waits so one dead mirror cannot hang the bootstrap.
rm -f /etc/apt/sources.list.d/*deadsnakes* 2>/dev/null || true
cat > /etc/apt/apt.conf.d/99tt-timeouts <<'APT'
Acquire::http::Timeout "20";
Acquire::https::Timeout "20";
Acquire::Retries "2";
APT

find_chrome() {
  command -v google-chrome-stable || command -v google-chrome || command -v chromium-browser || command -v chromium || true
}

install_chrome() {
  local existing
  existing=$(find_chrome)
  if [ -n "$existing" ]; then
    log "chrome already present: $existing"
    return 0
  fi
  local deb=/tmp/google-chrome-stable_current_amd64.deb
  local url=https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  local i
  for i in 1 2 3; do
    log "chrome .deb download try $i/3"
    rm -f "$deb"
    if run_to 120 curl -fL --connect-timeout 20 --retry 2 --retry-delay 3 -o "$deb" "$url" \
      && [ -s "$deb" ] && run_to 180 apt-get install -y "$deb"; then
      rm -f "$deb"
      log "chrome installed from .deb"
      return 0
    fi
    log "chrome .deb try $i failed"
    sleep $((i * 4))
  done
  log "chrome .deb failed; trying apt repo"
  run_to 60 bash -c 'curl -fsSL --connect-timeout 15 https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg'
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  run_to 90 apt-get update -qq
  run_to 180 apt-get install -y google-chrome-stable
}

log "installing apt deps"
run_to 180 apt-get update -qq
run_to 300 apt-get install -y -qq ffmpeg curl ca-certificates gnupg unzip xz-utils fonts-dejavu-core \
  libnss3 libatk-bridge2.0-0 libgtk-3-0 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 \
  libgbm1 libpangocairo-1.0-0 libxshmfence1 libglu1-mesa libegl1 libgles2 libgl1 \
  mesa-vulkan-drivers vulkan-tools libvulkan1 \
  || run_to 300 apt-get install -y -qq ffmpeg curl ca-certificates gnupg fonts-dejavu-core \
  libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1 libegl1 libgles2 libgl1
run_to 60 apt-get install -y -qq libasound2t64 || run_to 60 apt-get install -y -qq libasound2 || true

install_chrome
if ! find_chrome >/dev/null || [ -z "$(find_chrome)" ]; then
  echo "FATAL: Chrome/Chromium not installed" >&2
  exit 2
fi
if ! command -v node >/dev/null; then
  log "installing Node 20"
  run_to 180 bash -c 'curl -fsSL --connect-timeout 15 https://deb.nodesource.com/setup_20.x | bash -'
  run_to 180 apt-get install -y -qq nodejs
fi
python3 - <<'PY' 2>/dev/null || pip3 install -q librosa soundfile scipy numpy
import librosa, soundfile, scipy, numpy
print('py deps ok')
PY

log "locating NVIDIA EGL/GLX/Vulkan libs"
EGL_LIB=$(find /usr/lib /usr/lib64 -name 'libEGL_nvidia.so.0' 2>/dev/null | head -1 || true)
GLX_LIB=$(find /usr/lib /usr/lib64 -name 'libGLX_nvidia.so.0' 2>/dev/null | head -1 || true)
log "EGL_LIB=${EGL_LIB:-none} GLX_LIB=${GLX_LIB:-none}"
ldconfig -p 2>/dev/null | grep -iE 'EGL_nvidia|GLX_nvidia|nvidia.*vulkan|libvulkan' | head -20 || true

# System ICD dirs are often read-only on Runpod images — write ours under /tmp and point the loaders there.
EGL_DIR=/tmp/egl_vendor.d
VK_DIR=/tmp/vulkan_icd.d
mkdir -p "$EGL_DIR" "$VK_DIR"

if [ -n "$EGL_LIB" ]; then
  cat > "$EGL_DIR/10_nvidia.json" <<JSON
{ "file_format_version" : "1.0.0", "ICD" : { "library_path" : "${EGL_LIB}" } }
JSON
else
  cat > "$EGL_DIR/10_nvidia.json" <<'JSON'
{ "file_format_version" : "1.0.0", "ICD" : { "library_path" : "libEGL_nvidia.so.0" } }
JSON
fi
export __EGL_VENDOR_LIBRARY_DIRS="$EGL_DIR${__EGL_VENDOR_LIBRARY_DIRS:+:$__EGL_VENDOR_LIBRARY_DIRS}"
export __EGL_VENDOR_LIBRARY_FILENAMES="$EGL_DIR/10_nvidia.json"
log "EGL ICD -> $EGL_DIR/10_nvidia.json (__EGL_VENDOR_LIBRARY_DIRS=$__EGL_VENDOR_LIBRARY_DIRS)"

# Prefer the host-provided nvidia_icd.json if readable; else synthesize one.
if [ -r /etc/vulkan/icd.d/nvidia_icd.json ]; then
  cp /etc/vulkan/icd.d/nvidia_icd.json "$VK_DIR/nvidia_icd.json"
elif [ -r /usr/share/vulkan/icd.d/nvidia_icd.json ]; then
  cp /usr/share/vulkan/icd.d/nvidia_icd.json "$VK_DIR/nvidia_icd.json"
else
  VK_PATH=${GLX_LIB:-libGLX_nvidia.so.0}
  cat > "$VK_DIR/nvidia_icd.json" <<JSON
{ "file_format_version": "1.0.0", "ICD": { "library_path": "${VK_PATH}", "api_version": "1.3.0" } }
JSON
fi
export VK_ICD_FILENAMES="$VK_DIR/nvidia_icd.json${VK_ICD_FILENAMES:+:$VK_ICD_FILENAMES}"
log "Vulkan ICD -> $VK_ICD_FILENAMES"
# Persist for later shells (remote_run / render)
cat > /tmp/tt_gl_env.sh <<ENV
export NVIDIA_DRIVER_CAPABILITIES="$NVIDIA_DRIVER_CAPABILITIES"
export NVIDIA_VISIBLE_DEVICES="$NVIDIA_VISIBLE_DEVICES"
export __EGL_VENDOR_LIBRARY_DIRS="$__EGL_VENDOR_LIBRARY_DIRS"
export __EGL_VENDOR_LIBRARY_FILENAMES="$__EGL_VENDOR_LIBRARY_FILENAMES"
export VK_ICD_FILENAMES="$VK_ICD_FILENAMES"
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia
export CHROME_PATH="$(find_chrome)"
ENV
# shellcheck disable=SC1091
source /tmp/tt_gl_env.sh

command -v vulkaninfo >/dev/null && vulkaninfo --summary 2>/dev/null | head -40 || log "vulkaninfo unavailable/failed"

CHROME_BIN=$(find_chrome)
export CHROME_PATH=$CHROME_BIN
log "chrome=$CHROME_BIN node=$(node -v) ffmpeg=$(ffmpeg -version | head -1)"
HERE=$(cd "$(dirname "$0")" && pwd)
if [ ! -d "$HERE/node_modules/puppeteer-core" ]; then
  log "npm i puppeteer-core"
  (cd "$HERE" && npm i --omit=dev --no-audit --no-fund >/dev/null)
fi
log "bootstrap ok"
