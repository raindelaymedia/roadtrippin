"""
Road Trippin' — Generate index.html for GitHub Pages
Just a thin wrapper around build_dashboard.py that outputs index.html.

Usage:
    python build_index.py

Drop index.html in your repo root and GitHub Pages will serve it.
"""

import os
import subprocess
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
data_dir   = os.path.join(script_dir, "data")

# Find build_dashboard.py in same folder
dashboard_script = os.path.join(script_dir, "build_dashboard.py")
if not os.path.exists(dashboard_script):
    raise SystemExit("build_dashboard.py not found in the same folder.")

# Run build_dashboard.py with output set to index.html
result = subprocess.run(
    [sys.executable, dashboard_script, "--output", "index.html"],
    cwd=script_dir,
)

if result.returncode == 0:
    print(f"\n✓ index.html ready for GitHub Pages commit")
else:
    print(f"\n✗ build_dashboard.py exited with code {result.returncode}")