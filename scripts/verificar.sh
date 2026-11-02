#!/usr/bin/env bash
set -euo pipefail
python -m compileall -q src
python -m pytest -q
git status --short || true
