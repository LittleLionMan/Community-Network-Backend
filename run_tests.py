import subprocess
import sys
import os

def run_tests():
    """Run all tests with proper setup"""

    print("🧪 Starting Community Platform Tests...")
    print("=" * 60)

    if not os.path.exists("app"):
        print("❌ Error: Please run this script from the project root directory")
        print("   (Should contain app/ folder)")
        return 1

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
    os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
    os.environ["DEBUG"] = "true"
    os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"

    test_command = [
        "python", "-m", "pytest",
        "app/tests/",
        "-v",
        "--tb=short",
        "--disable-warnings",
        "-x"
    ]

    print(f"🚀 Running command: {' '.join(test_command)}")
    print("-" * 60)

    try:
        result = subprocess.run(test_command, timeout=300)

        if result.returncode == 0:
            print("\n🎉 All tests passed!")
            return 0
        else:
            print(f"\n❌ Tests failed with exit code {result.returncode}")
            return result.returncode

    except subprocess.TimeoutExpired:
        print("\n⏰ Tests timed out after 5 minutes")
        return 1
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Error running tests: {e}")
        return 1

def run_single_test(test_name):
    if not os.path.exists("app"):
        print("❌ Error: Please run this script from the project root directory")
        return 1

    test_path = f"app/tests/test_{test_name}.py"
    if not os.path.exists(test_path):
        print(f"❌ Test file {test_path} not found")
        available_tests = []
        if os.path.exists("app/tests"):
            available_tests = [
                f.replace("test_", "").replace(".py", "")
                for f in os.listdir("app/tests")
                if f.startswith("test_") and f.endswith(".py")
            ]
        print(f"Available tests: {', '.join(available_tests)}")
        return 1

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
    os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
    os.environ["DEBUG"] = "true"
    os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"

    print(f"🧪 Running single test: {test_name}")
    print("=" * 40)

    result = subprocess.run([
        "python", "-m", "pytest",
        test_path,
        "-v",
        "--tb=short",
        "--disable-warnings"
    ])

    return result.returncode

def run_auth_test():
    print("🔐 Running all auth test...")

    result = subprocess.run([
        "python", "-m", "pytest",
        "app/tests/test_auth.py",
        "-v", "-s"
    ])

    return result.returncode

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "auth":
            exit_code = run_auth_test()
        else:
            test_name = sys.argv[1]
            exit_code = run_single_test(test_name)
    else:
        exit_code = run_tests()

    sys.exit(exit_code)
