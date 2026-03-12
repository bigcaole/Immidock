#!/usr/bin/env bash
set -euo pipefail

pyinstaller --onefile -n immidock dockshifter/cli/main.py
