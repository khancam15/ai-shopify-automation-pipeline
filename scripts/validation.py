"""
validation.py — Input validation and sanitization
──────────────────────────────────────────────────
Prevents path traversal, injection attacks, and invalid data from
entering the pipeline.

Usage:
    from validation import validate_product_name, validate_price

    product = validate_product_name(sys.argv[1])  # Raises ValueError if invalid
    price = validate_price(form_data.get("price"))
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


# ── Product Name Validation ───────────────────────────────────────────────────

def validate_product_name(name: str | None, *, max_length: int = 100) -> str:
    r"""
    Validate and sanitize a product name for use in file paths and database.

    Rules:
      • Must be 1-100 characters (configurable)
      • Allowed: letters, numbers, spaces, hyphens, underscores
      • No path traversal sequences (../, ..\, etc.)
      • No leading/trailing whitespace
      • No consecutive spaces

    Args:
        name: Raw product name from user input
        max_length: Maximum allowed length

    Returns:
        Sanitized product name

    Raises:
        ValidationError: If name is invalid

    Examples:
        >>> validate_product_name("Social Media Bundle")
        'Social Media Bundle'

        >>> validate_product_name("../../../etc/passwd")
        ValidationError: Invalid characters in product name

        >>> validate_product_name("  Extra   Spaces  ")
        'Extra Spaces'
    """
    if not name or not isinstance(name, str):
        raise ValidationError("Product name is required and must be a string")

    # Strip whitespace
    name = name.strip()

    # Check length
    if not (1 <= len(name) <= max_length):
        raise ValidationError(
            f"Product name must be 1-{max_length} characters, got {len(name)}"
        )

    # Check for path traversal
    if ".." in name or "/" in name or "\\" in name:
        raise ValidationError(
            "Product name cannot contain path traversal sequences (../, /, \\)"
        )

    # Check allowed characters
    if not re.match(r'^[a-zA-Z0-9 _-]+$', name):
        raise ValidationError(
            "Product name can only contain letters, numbers, spaces, hyphens, and underscores"
        )

    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name)

    # Additional checks for suspicious patterns
    suspicious = ["<script", "javascript:", "onerror=", "onclick="]
    name_lower = name.lower()
    for pattern in suspicious:
        if pattern in name_lower:
            raise ValidationError(f"Product name contains suspicious pattern: {pattern}")

    return name


def sanitize_product_name_for_path(name: str) -> str:
    """
    Convert a validated product name to a safe filesystem path component.

    Args:
        name: Product name (should already be validated)

    Returns:
        Safe path component (spaces replaced with underscores)

    Example:
        >>> sanitize_product_name_for_path("Social Media Bundle")
        'Social_Media_Bundle'
    """
    return name.replace(" ", "_")


# ── Price Validation ──────────────────────────────────────────────────────────

def validate_price(
    price: Any,
    *,
    min_price: float = 0.99,
    max_price: float = 999.99,
) -> float:
    """
    Validate a product price.

    Rules:
      • Must be numeric (int or float)
      • Must be within min/max range (default: $0.99 - $999.99)
      • Rounded to 2 decimal places

    Args:
        price: Raw price value
        min_price: Minimum allowed price
        max_price: Maximum allowed price

    Returns:
        Validated price as float

    Raises:
        ValidationError: If price is invalid
    """
    try:
        price_float = float(price)
    except (TypeError, ValueError):
        raise ValidationError(f"Price must be numeric, got: {type(price).__name__}")

    if not (min_price <= price_float <= max_price):
        raise ValidationError(
            f"Price must be between ${min_price:.2f} and ${max_price:.2f}, got ${price_float:.2f}"
        )

    return round(price_float, 2)


# ── URL Validation ────────────────────────────────────────────────────────────

def validate_url(url: str | None, *, required_schemes: tuple[str, ...] = ("http", "https")) -> str:
    """
    Validate a URL.

    Rules:
      • Must start with allowed scheme (default: http or https)
      • No javascript:, file:, or other dangerous schemes
      • Basic format check

    Args:
        url: URL to validate
        required_schemes: Tuple of allowed URL schemes

    Returns:
        Validated URL

    Raises:
        ValidationError: If URL is invalid
    """
    if not url or not isinstance(url, str):
        raise ValidationError("URL is required and must be a string")

    url = url.strip()

    # Check scheme
    if not any(url.startswith(f"{scheme}://") for scheme in required_schemes):
        allowed = ", ".join(required_schemes)
        raise ValidationError(f"URL must start with one of: {allowed}")

    # Block dangerous schemes
    dangerous = ["javascript:", "file:", "data:", "vbscript:"]
    url_lower = url.lower()
    for scheme in dangerous:
        if url_lower.startswith(scheme):
            raise ValidationError(f"Dangerous URL scheme not allowed: {scheme}")

    # Basic length check
    if len(url) > 2048:
        raise ValidationError("URL is too long (max 2048 characters)")

    return url


# ── Email Validation ──────────────────────────────────────────────────────────

def validate_email(email: str | None) -> str:
    """
    Basic email validation.

    Note: This is NOT RFC 5322 compliant, but good enough for most cases.
    For production, consider using a library like email-validator.

    Args:
        email: Email address to validate

    Returns:
        Validated email (lowercased)

    Raises:
        ValidationError: If email is invalid
    """
    if not email or not isinstance(email, str):
        raise ValidationError("Email is required and must be a string")

    email = email.strip().lower()

    # Simple regex check
    pattern = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError(f"Invalid email format: {email}")

    if len(email) > 254:
        raise ValidationError("Email is too long (max 254 characters)")

    return email


# ── File Path Validation ──────────────────────────────────────────────────────

def validate_file_path(
    path: str | Path,
    *,
    must_exist: bool = False,
    allowed_extensions: tuple[str, ...] | None = None,
    base_dir: Path | None = None,
) -> Path:
    """
    Validate a file path for security.

    Rules:
      • No path traversal (../)
      • Optionally check if file exists
      • Optionally restrict to specific file extensions
      • Optionally ensure path is within a base directory

    Args:
        path: File path to validate
        must_exist: If True, raise error if file doesn't exist
        allowed_extensions: If provided, restrict to these extensions (e.g., (".jpg", ".png"))
        base_dir: If provided, ensure path is within this directory

    Returns:
        Validated Path object

    Raises:
        ValidationError: If path is invalid or dangerous
    """
    if not path:
        raise ValidationError("File path is required")

    # Convert to Path object
    file_path = Path(path) if isinstance(path, str) else path

    # Resolve to absolute path
    try:
        resolved = file_path.resolve()
    except (OSError, RuntimeError) as e:
        raise ValidationError(f"Invalid file path: {e}")

    # Check for path traversal
    if ".." in file_path.parts:
        raise ValidationError("Path traversal not allowed (..)")

    # Check base directory restriction
    if base_dir:
        try:
            resolved.relative_to(base_dir.resolve())
        except ValueError:
            raise ValidationError(f"Path must be within {base_dir}")

    # Check existence
    if must_exist and not resolved.exists():
        raise ValidationError(f"File not found: {resolved}")

    # Check extension
    if allowed_extensions:
        if resolved.suffix.lower() not in [ext.lower() for ext in allowed_extensions]:
            raise ValidationError(
                f"File extension must be one of {allowed_extensions}, got {resolved.suffix}"
            )

    return resolved


# ── Test function ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test product name validation
    print("Testing product name validation:")
    try:
        print(f"✅ Valid: {validate_product_name('Social Media Bundle')}")
        print(f"✅ Sanitized: {sanitize_product_name_for_path('Social Media Bundle')}")
    except ValidationError as e:
        print(f"❌ {e}")

    try:
        validate_product_name("../../../etc/passwd")
    except ValidationError as e:
        print(f"✅ Blocked path traversal: {e}")

    # Test price validation
    print("\nTesting price validation:")
    try:
        print(f"✅ Valid price: ${validate_price(9.99):.2f}")
        print(f"✅ Valid price: ${validate_price('19.99'):.2f}")
    except ValidationError as e:
        print(f"❌ {e}")

    try:
        validate_price(0.50)
    except ValidationError as e:
        print(f"✅ Blocked low price: {e}")

    # Test URL validation
    print("\nTesting URL validation:")
    try:
        print(f"✅ Valid URL: {validate_url('https://example.com')}")
    except ValidationError as e:
        print(f"❌ {e}")

    try:
        validate_url("javascript:alert('xss')")
    except ValidationError as e:
        print(f"✅ Blocked dangerous URL: {e}")

    print("\n✅ Validation tests complete")
