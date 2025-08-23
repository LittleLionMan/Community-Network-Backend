import subprocess
import sys
import os
import time

def run_tests():

    print("🧪 Starting Community Platform Tests...")
    print("=" * 60)

    # ÄNDERUNG: Ensure we're in the right directory
    if not os.path.exists("app"):
        print("❌ Error: Please run this script from the project root directory")
        print("   (Should contain app/ folder)")
        return 1

    test_files = [
        "app/tests/test_health.py",
        "app/tests/test_auth.py",
        "app/tests/test_event_categories.py",
        "app/tests/test_events.py",
        "app/tests/test_services.py",
        "app/tests/test_discussions.py",
        "app/tests/test_comments.py",
        "app/tests/test_polls.py"
    ]

    results = {}

    os.chdir("app")

    for test_file in test_files:
        print(f"\n📋 Running {test_file}...")
        try:
            test_path = test_file.replace("app/", "")

            result = subprocess.run(
                ["python", "-m", "pytest", test_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                print(f"✅ {test_file} - PASSED")
                results[test_file] = "PASSED"
            else:
                print(f"❌ {test_file} - FAILED")
                if result.stdout:
                    print(f"📄 Output: {result.stdout}")
                if result.stderr:
                    print(f"🚨 Errors: {result.stderr}")
                results[test_file] = "FAILED"

        except subprocess.TimeoutExpired:
            print(f"⏰ {test_file} - TIMEOUT")
            results[test_file] = "TIMEOUT"
        except Exception as e:
            print(f"💥 {test_file} - ERROR: {e}")
            results[test_file] = "ERROR"

        time.sleep(2)
    os.chdir("..")

    print("\n" + "=" * 60)
    print("📊 FINAL TEST SUMMARY:")
    print("=" * 60)

    passed = sum(1 for r in results.values() if r == "PASSED")
    failed = sum(1 for r in results.values() if r == "FAILED")
    errors = sum(1 for r in results.values() if r == "ERROR")
    timeouts = sum(1 for r in results.values() if r == "TIMEOUT")

    for test_file, result in results.items():
        if result == "PASSED":
            status_emoji = "✅"
        elif result == "FAILED":
            status_emoji = "❌"
        elif result == "TIMEOUT":
            status_emoji = "⏰"
        else:
            status_emoji = "💥"

        print(f"{status_emoji} {test_file}: {result}")

    print(f"\n📈 Results: {passed} passed, {failed} failed, {errors} errors, {timeouts} timeouts")

    if failed == 0 and errors == 0 and timeouts == 0:
        print("🎉 All tests passed! Community Platform is working correctly.")
        return 0
    else:
        print("🚨 Some tests failed - check output above for details")
        print("💡 Note: Rate limiting (429) errors are expected during rapid testing")
        return 1

def run_single_test(test_name):
    """Run a single test file"""
    if not os.path.exists("app"):
        print("❌ Error: Please run this script from the project root directory")
        return 1

    test_path = f"app/tests/test_{test_name}.py"
    if not os.path.exists(test_path):
        print(f"❌ Test file {test_path} not found")
        available_tests = [f.replace("test_", "").replace(".py", "")
                          for f in os.listdir("app/tests")
                          if f.startswith("test_") and f.endswith(".py")]
        print(f"Available tests: {', '.join(available_tests)}")
        return 1

    print(f"🧪 Running single test: {test_name}")
    print("=" * 40)

    os.chdir("app")
    result = subprocess.run(["python", "-m", "pytest", f"tests/test_{test_name}.py", "-v"])
    os.chdir("..")

    return result.returncode

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        exit_code = run_single_test(test_name)
    else:
        exit_code = run_tests()

    sys.exit(exit_code)
