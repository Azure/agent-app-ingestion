"""Offline destination selection for both deployment scripts."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("rg-app", 0, "rg-app"),
    ("", 0, "rg-legacy"),
    ("  ", 0, "rg-legacy"),
    ("", 1, None),
    ("rg-app\nrg-other", 0, None),
)


class DeploymentResourceGroupTests(unittest.TestCase):
    def run_cases(self, command, source):
        for value, status, expected in CASES:
            with self.subTest(value=value, status=status):
                result = subprocess.run(
                    [*command, source], capture_output=True, text=True, timeout=15,
                    env={**os.environ, "RG_TEST_VALUE": value, "RG_TEST_EXIT": str(status)},
                )
                if expected is None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("rg-legacy", result.stdout)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is unavailable")
    def test_powershell(self):
        source = (ROOT / "scripts/deploy.ps1").read_text(encoding="utf-8-sig")
        resolver = re.search(
            r"^function Get-ApplicationResourceGroup \{.*?^\}", source, re.M | re.S,
        ).group()
        self.assertIn("AZURE_APP_RESOURCE_GROUP = (Get-ApplicationResourceGroup)", source)
        self.assertNotIn("$values.AZURE_RESOURCE_GROUP", source)
        driver = """
$ErrorActionPreference = 'Stop'
function az {
    $global:LASTEXITCODE = [int]$env:RG_TEST_EXIT
    if ($env:RG_TEST_VALUE) { $env:RG_TEST_VALUE -split "`n" }
}
function Get-RequiredConfigValue { param($Key); 'rg-legacy' }
"""
        self.run_cases(
            [shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-Command"],
            driver + resolver + "\nGet-ApplicationResourceGroup",
        )

    @unittest.skipUnless(shutil.which("bash"), "Bash is unavailable")
    def test_shell(self):
        source = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8-sig")
        resolver = re.search(
            r"^get_application_resource_group\(\) \{.*?^\}", source, re.M | re.S,
        ).group()
        self.assertIn('resourceGroupName="$(get_application_resource_group)"', source)
        driver = """
az() { printf '%s' "$RG_TEST_VALUE"; return "$RG_TEST_EXIT"; }
require_config_value() { printf 'rg-legacy'; }
error() { printf '%s\\n' "$*" >&2; }
APP_CONFIG_ENDPOINT=https://example.azconfig.io
"""
        self.run_cases([shutil.which("bash"), "-c"], driver + resolver + "\nget_application_resource_group")


if __name__ == "__main__":
    unittest.main()
