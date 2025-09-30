import os
import sys
from pathlib import Path
import json
from typing import TypedDict

def _validate_secret_key(value: str) -> bool:
    return len(value) >= 32 and value != 'CHANGE_THIS_TO_A_SECURE_RANDOM_KEY_IN_PRODUCTION'

def _validate_database_url(value: str) -> bool:
    return value.startswith(('postgresql', 'sqlite'))

def _validate_smtp_host(value: str) -> bool:
    return len(value) > 0

def _validate_sentry_dsn(value: str) -> bool:
    return value.startswith('https://')

def _validate_debug_setting(value: str, environment: str) -> bool:
    return value.lower() != 'true' if environment == 'production' else True

def _validate_docs_setting(value: str, environment: str) -> bool:
    return value.lower() != 'true' if environment == 'production' else True

class ConfigurationError(Exception):
    pass

class ValidationResult(TypedDict):
    environment: str
    errors: list[str]
    warnings: list[str]
    valid: bool

class EnvironmentValidator:

    REQUIRED_SETTINGS: dict[str, dict[str, object]] = {
        'SECRET_KEY': {
            'description': 'JWT signing secret key',
            'validation': _validate_secret_key,
            'error': 'SECRET_KEY must be at least 32 characters and changed from default'
        },
        'DATABASE_URL': {
            'description': 'Database connection URL',
            'validation': _validate_database_url,
            'error': 'DATABASE_URL must be a valid PostgreSQL or SQLite URL'
        }
    }

    PRODUCTION_REQUIRED: dict[str, dict[str, object]] = {
        'SMTP_HOST': {
            'description': 'Email server hostname',
            'validation': _validate_smtp_host,
            'error': 'SMTP_HOST is required in production'
        },
        'SENTRY_DSN': {
            'description': 'Error monitoring DSN',
            'validation': _validate_sentry_dsn,
            'error': 'SENTRY_DSN should be configured for production monitoring'
        }
    }

    SECURITY_CHECKS: dict[str, dict[str, object]] = {
        'DEBUG': {
            'description': 'Debug mode setting',
            'validation': _validate_debug_setting,
            'error': 'DEBUG must be false in production environment'
        },
        'DOCS_ENABLED': {
            'description': 'API documentation endpoints',
            'validation': _validate_docs_setting,
            'error': 'DOCS_ENABLED should be false in production'
        }
    }

    @classmethod
    def validate_environment(cls) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        environment = os.getenv('ENVIRONMENT', 'development').lower()

        for setting, config in cls.REQUIRED_SETTINGS.items():
            value = os.getenv(setting)
            if not value:
                errors.append(f"❌ {setting} is required: {config['description']}")
            validation_func = config.get('validation')
            if callable(validation_func):
                if not validation_func(value):
                    errors.append(f"❌ {setting}: {config['error']}")
            else:
                errors.append(f"❌ {setting}: Invalid validation configuration")

        if environment == 'production':
            for setting, config in cls.PRODUCTION_REQUIRED.items():
                value = os.getenv(setting)
                validation_func = config.get('validation')
                if not value or (callable(validation_func) and not validation_func(value)):
                    warnings.append(f"⚠️ {setting}: {config['error']}")

        for setting, config in cls.SECURITY_CHECKS.items():
            value = os.getenv(setting, '')
            validation_func = config.get('validation')
            if callable(validation_func):
                if not validation_func(value, environment):
                    if environment == 'production':
                        errors.append(f"❌ {setting}: {config['error']}")
                    else:
                        warnings.append(f"⚠️ {setting}: {config['error']}")

        upload_dir = os.getenv('UPLOAD_DIR', '/app/uploads')
        try:
            Path(upload_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"❌ UPLOAD_DIR '{upload_dir}' cannot be created: {e}")

        db_url = os.getenv('DATABASE_URL', '')
        if db_url:
            try:
                valid_schemes = ['postgresql+asyncpg:', 'sqlite+aiosqlite:', 'sqlite:']
                if not any(db_url.startswith(scheme) for scheme in valid_schemes):
                    errors.append("❌ DATABASE_URL must start with postgresql+asyncpg:// or sqlite+aiosqlite:///")
            except Exception:
                errors.append("❌ DATABASE_URL cannot be parsed")

        cors_origins = os.getenv('BACKEND_CORS_ORIGINS', '[]')
        try:
            origins = json.loads(cors_origins) # type: ignore[misc]
            if not isinstance(origins, list):
                warnings.append("⚠️ BACKEND_CORS_ORIGINS should be a JSON array")

        except json.JSONDecodeError:
            warnings.append("⚠️ BACKEND_CORS_ORIGINS is not valid JSON")

        numeric_settings = {
            'MAX_FILE_SIZE': (1024, 50 * 1024 * 1024),
            'RATE_LIMIT_PER_MINUTE': (1, 10000),
            'ACCESS_TOKEN_EXPIRE_MINUTES': (5, 1440)
        }

        for setting, (min_val, max_val) in numeric_settings.items():
            value = os.getenv(setting)
            if value:
                try:
                    num_value = int(value)
                    if not (min_val <= num_value <= max_val):
                        warnings.append(f"⚠️ {setting} should be between {min_val} and {max_val}")
                except ValueError:
                    warnings.append(f"⚠️ {setting} should be a number")

        return ValidationResult(
            environment=environment,
            errors=errors,
            warnings=warnings,
            valid=len(errors) == 0
        )

    @classmethod
    def validate_or_exit(cls) -> None:
        skip_validation = (
            os.getenv('SKIP_CONFIG_VALIDATION', '').lower() == 'true' or
            'alembic' in sys.argv[0] or
            any('alembic' in arg for arg in sys.argv)
        )

        if skip_validation:
            print("🔧 Skipping configuration validation for migration tool")
            return

        result = cls.validate_environment()

        print("🔧 Environment Configuration Validation")
        print("=" * 50)
        environment = result.get('environment', 'unknown')
        print(f"Environment: {environment.upper()}")


        result = cls.validate_environment()

        print("🔧 Environment Configuration Validation")
        print("=" * 50)
        environment = result.get('environment', 'unknown')
        print(f"Environment: {environment.upper()}")


        if result['warnings']:
            print("\n⚠️ WARNINGS:")
            for warning in result['warnings']:
                print(f"  {warning}")

        if result['errors']:
            print("\n❌ CRITICAL ERRORS:")
            for error in result['errors']:
                print(f"  {error}")

            print("\n💡 To fix these issues:")
            print("  1. Copy .env.example to .env")
            print("  2. Configure the required settings")
            print("  3. Generate a secure SECRET_KEY:")
            print("     python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
            print("\nApplication cannot start with configuration errors.")
            sys.exit(1)

        if not result['warnings']:
            print("\n✅ All configuration checks passed!")

        print("-" * 50)
