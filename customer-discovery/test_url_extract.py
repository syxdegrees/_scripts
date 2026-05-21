import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT = str(Path(__file__).parent / 'url_extract.py')


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, SCRIPT, '--help'],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert '--run_id' in result.stdout


def test_missing_run_id_exits_nonzero():
    result = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True, text=True
    )
    assert result.returncode != 0


def test_summary_only_flag_accepted():
    # With no env vars set, should error on SUPABASE_URL — not on unknown flag
    result = subprocess.run(
        [sys.executable, SCRIPT, '--run_id', 'test-uuid', '--summary-only'],
        capture_output=True, text=True,
        env={'PATH': __import__('os').environ.get('PATH', '')}  # strip env vars
    )
    # Should fail on missing SUPABASE_URL, not on unrecognized --summary-only
    assert 'SUPABASE_URL' in result.stderr or result.returncode != 0
    assert 'unrecognized' not in result.stderr
