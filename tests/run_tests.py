#!/usr/bin/env python3
"""
Convenient test runner for Xero workflow E2E tests.

Usage:
    # Run all tests in headless mode (requires Xero login)
    python tests/run_tests.py --live

    # Run all tests with visible browser
    python tests/run_tests.py --live --headed

    # Run specific report tests
    python tests/run_tests.py --live --report trial_balance

    # Run with slow motion for debugging
    python tests/run_tests.py --live --headed --slow-mo 500

    # Run only selector validation tests
    python tests/run_tests.py --live -k "selector"

    # Run only end-to-end tests
    python tests/run_tests.py --live -k "end_to_end"
"""
import argparse
import subprocess
import sys
from pathlib import Path


REPORTS = [
    "trial_balance",
    "profit_and_loss",
    "aged_receivables",
    "aged_payables",
    "account_transactions",
]


def main():
    parser = argparse.ArgumentParser(description="Run Xero workflow E2E tests")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run tests against live Xero (requires browser login)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run with visible browser window",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Slow down operations by milliseconds",
    )
    parser.add_argument(
        "--report",
        choices=REPORTS + ["all"],
        default="all",
        help="Which report workflow to test",
    )
    parser.add_argument(
        "-k",
        "--filter",
        type=str,
        help="pytest -k filter expression",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--html",
        type=str,
        help="Generate HTML report to specified path",
    )

    args = parser.parse_args()

    tests_dir = Path(__file__).parent
    cmd = ["python", "-m", "pytest", str(tests_dir)]

    if args.live:
        cmd.append("--live")

    if args.headed:
        cmd.append("--headed")

    if args.slow_mo:
        cmd.extend(["--slow-mo", str(args.slow_mo)])

    if args.verbose:
        cmd.append("-v")

    if args.report != "all":
        cmd.extend(["-k", f"Test{args.report.replace('_', '').title()}"])

    if args.filter:
        if "-k" in cmd:
            idx = cmd.index("-k")
            cmd[idx + 1] = f"({cmd[idx + 1]}) and ({args.filter})"
        else:
            cmd.extend(["-k", args.filter])

    if args.html:
        cmd.extend(["--html", args.html, "--self-contained-html"])

    cmd.extend(["--tb=short", "-x"])

    print(f"Running: {' '.join(cmd)}")
    print("-" * 60)

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
