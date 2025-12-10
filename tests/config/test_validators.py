import re
from decimal import Decimal

import pytest

from aioscraper.config.field_validators import (
    ChainValidator,
    ChoicesValidator,
    CustomValidator,
    LengthValidator,
    ProxyValidator,
    RangeValidator,
    RegexValidator,
)


class TestRangeValidator:
    def test_validates_min_int(self):
        validator = RangeValidator[int](min_value=1)

        assert validator("port", 1) == 1
        assert validator("port", 100) == 100

        with pytest.raises(ValueError, match="minimum is 1"):
            validator("port", 0)

    def test_validates_max_int(self):
        validator = RangeValidator[int](max_value=100)

        assert validator("port", 100) == 100
        assert validator("port", 50) == 50

        with pytest.raises(ValueError, match="maximum is 100"):
            validator("port", 101)

    def test_validates_min_max_int(self):
        validator = RangeValidator[int](min_value=1, max_value=65535)

        assert validator("port", 1) == 1
        assert validator("port", 8080) == 8080
        assert validator("port", 65535) == 65535

        with pytest.raises(ValueError, match="minimum is 1"):
            validator("port", 0)

        with pytest.raises(ValueError, match="maximum is 65535"):
            validator("port", 65536)

    def test_validates_float_range(self):
        validator = RangeValidator[float](min_value=0.0, max_value=1.0)

        assert validator("threshold", 0.0) == 0.0
        assert validator("threshold", 0.5) == 0.5
        assert validator("threshold", 1.0) == 1.0

        with pytest.raises(ValueError, match=r"minimum is 0.0"):
            validator("threshold", -0.1)

        with pytest.raises(ValueError, match=r"maximum is 1.0"):
            validator("threshold", 1.1)

    def test_validates_decimal_range(self):
        validator = RangeValidator[Decimal](min_value=Decimal("0.01"), max_value=Decimal("999.99"))

        assert validator("price", Decimal("0.01")) == Decimal("0.01")
        assert validator("price", Decimal("50.00")) == Decimal("50.00")
        assert validator("price", Decimal("999.99")) == Decimal("999.99")

        with pytest.raises(ValueError, match=r"minimum is 0.01"):
            validator("price", Decimal("0.00"))

        with pytest.raises(ValueError, match=r"maximum is 999.99"):
            validator("price", Decimal("1000.00"))

    def test_handles_none_when_no_constraints_violated(self):
        validator = RangeValidator[int](min_value=1, max_value=100)
        assert validator("value", None) is None

    def test_requires_at_least_one_constraint(self):
        with pytest.raises(ValueError, match="At least one of min or max must be specified"):
            RangeValidator[int]()


class TestLengthValidator:
    def test_validates_min_string_length(self):
        validator = LengthValidator(min_length=5)

        assert validator("api_key", "12345") == "12345"
        assert validator("api_key", "123456") == "123456"

        with pytest.raises(ValueError, match="minimum is 5"):
            validator("api_key", "1234")

    def test_validates_max_string_length(self):
        validator = LengthValidator(max_length=10)

        assert validator("name", "1234567890") == "1234567890"
        assert validator("name", "12345") == "12345"

        with pytest.raises(ValueError, match="maximum is 10"):
            validator("name", "12345678901")

    def test_validates_min_max_string_length(self):
        validator = LengthValidator(min_length=3, max_length=10)

        assert validator("username", "abc") == "abc"
        assert validator("username", "abcdef") == "abcdef"
        assert validator("username", "abcdefghij") == "abcdefghij"

        with pytest.raises(ValueError, match="minimum is 3"):
            validator("username", "ab")

        with pytest.raises(ValueError, match="maximum is 10"):
            validator("username", "abcdefghijk")

    def test_validates_list_length(self):
        validator = LengthValidator(min_length=1, max_length=5)

        assert validator("items", [1]) == [1]
        assert validator("items", [1, 2, 3]) == [1, 2, 3]
        assert validator("items", [1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]

        with pytest.raises(ValueError, match="minimum is 1"):
            validator("items", [])

        with pytest.raises(ValueError, match="maximum is 5"):
            validator("items", [1, 2, 3, 4, 5, 6])

    def test_validates_tuple_length(self):
        validator = LengthValidator(min_length=2, max_length=3)

        assert validator("coords", (1, 2)) == (1, 2)
        assert validator("coords", (1, 2, 3)) == (1, 2, 3)

        with pytest.raises(ValueError, match="minimum is 2"):
            validator("coords", (1,))

        with pytest.raises(ValueError, match="maximum is 3"):
            validator("coords", (1, 2, 3, 4))

    def test_requires_at_least_one_constraint(self):
        with pytest.raises(ValueError, match="At least one of min or max must be specified"):
            LengthValidator()

    def test_rejects_negative_min(self):
        with pytest.raises(ValueError, match="min must be non-negative"):
            LengthValidator(min_length=-1)

    def test_rejects_negative_max(self):
        with pytest.raises(ValueError, match="max must be non-negative"):
            LengthValidator(max_length=-1)

    def test_rejects_min_greater_than_max(self):
        with pytest.raises(ValueError, match="min cannot be greater than max"):
            LengthValidator(min_length=10, max_length=5)


class TestRegexValidator:
    def test_validates_matching_pattern(self):
        validator = RegexValidator(r"^https?://")

        assert validator("url", "http://example.com") == "http://example.com"
        assert validator("url", "https://example.com") == "https://example.com"

    def test_rejects_non_matching_pattern(self):
        validator = RegexValidator(r"^https?://")

        with pytest.raises(ValueError, match="does not match pattern"):
            validator("url", "ftp://example.com")

        with pytest.raises(ValueError, match="does not match pattern"):
            validator("url", "example.com")

    def test_supports_regex_flags(self):
        validator = RegexValidator(r"^HELLO$", flags=re.IGNORECASE)

        assert validator("greeting", "hello") == "hello"
        assert validator("greeting", "HELLO") == "HELLO"
        assert validator("greeting", "Hello") == "Hello"

        with pytest.raises(ValueError, match="does not match pattern"):
            validator("greeting", "hello world")


class TestChoicesValidator:
    def test_validates_allowed_value(self):
        validator = ChoicesValidator(["dev", "staging", "prod"])

        assert validator("env", "dev") == "dev"
        assert validator("env", "staging") == "staging"
        assert validator("env", "prod") == "prod"

    def test_rejects_disallowed_value(self):
        validator = ChoicesValidator(["dev", "staging", "prod"])

        with pytest.raises(ValueError, match="must be one of"):
            validator("env", "test")

    def test_accepts_set_of_choices(self):
        validator = ChoicesValidator({1, 2, 3})

        assert validator("number", 1) == 1
        assert validator("number", 2) == 2
        assert validator("number", 3) == 3

        with pytest.raises(ValueError, match="must be one of"):
            validator("number", 4)


class TestCustomValidator:
    def test_validates_with_function_returning_true(self):
        validator = CustomValidator(lambda x: x > 0)

        assert validator("value", 1) == 1
        assert validator("value", 100) == 100

    def test_rejects_with_function_returning_false(self):
        validator = CustomValidator(lambda x: x > 0)

        with pytest.raises(ValueError, match="Custom validation failed"):
            validator("value", 0)

        with pytest.raises(ValueError, match="Custom validation failed"):
            validator("value", -1)

    def test_validates_with_function_returning_transformed_value(self):
        validator = CustomValidator(lambda x: x.strip().upper())

        assert validator("name", "  hello  ") == "HELLO"
        assert validator("name", "world") == "WORLD"

    def test_handles_value_error_from_function(self):
        def check_even(x: int) -> int:
            if x % 2 != 0:
                raise ValueError("must be even")
            return x

        validator = CustomValidator(check_even)

        assert validator("number", 2) == 2
        assert validator("number", 4) == 4

        with pytest.raises(ValueError, match="must be even"):
            validator("number", 3)

    def test_wraps_other_exceptions(self):
        def failing_validator(x: int) -> int:
            raise RuntimeError("something went wrong")

        validator = CustomValidator(failing_validator)

        with pytest.raises(ValueError, match=r"Custom validation failed.*something went wrong"):
            validator("value", 1)


class TestChainValidator:
    def test_applies_validators_in_order(self):
        validator = ChainValidator(
            [
                RangeValidator[int](min_value=1, max_value=100),
                CustomValidator(lambda x: x if x % 2 == 0 else False),
            ],
        )

        assert validator("number", 2) == 2
        assert validator("number", 50) == 50
        assert validator("number", 100) == 100

        with pytest.raises(ValueError, match="minimum is 1"):
            validator("number", 0)

        with pytest.raises(ValueError, match="maximum is 100"):
            validator("number", 101)

        with pytest.raises(ValueError, match="Custom validation failed"):
            validator("number", 3)

    def test_passes_value_through_chain(self):
        validator = ChainValidator(
            [
                CustomValidator(lambda x: x.strip()),
                CustomValidator(lambda x: x.upper()),
                LengthValidator(min_length=3),
            ],
        )

        assert validator("name", "  hello  ") == "HELLO"

        with pytest.raises(ValueError, match="minimum is 3"):
            validator("name", "  hi  ")

    def test_requires_at_least_one_validator(self):
        with pytest.raises(ValueError, match="At least one validator must be provided"):
            ChainValidator([])


class TestProxyValidator:
    validator = ProxyValidator({"http", "https"})

    def test_accepts_none(self):
        assert self.validator("proxy", None) is None

    def test_accepts_valid_http_url(self):
        assert self.validator("proxy", "http://proxy:8080") == "http://proxy:8080"

    def test_accepts_valid_https_url(self):
        assert self.validator("proxy", "https://proxy:8443") == "https://proxy:8443"

    def test_accepts_url_with_credentials(self):
        assert self.validator("proxy", "http://user:pass@proxy:8080") == "http://user:pass@proxy:8080"

    def test_rejects_invalid_url(self):
        with pytest.raises(ValueError, match="Proxy URL must include a scheme"):
            self.validator("proxy", "not-a-url")

        with pytest.raises(ValueError, match="Invalid proxy URL"):
            self.validator("proxy", "http://[::1")  # malformed IPv6

    def test_accepts_dict_with_http_and_https(self):
        proxy_dict: dict[str, str | None] = {"http": "http://p1:8080", "https": "http://p2:8080"}

        result = self.validator("proxy", proxy_dict)
        assert result == {"http://": "http://p1:8080", "https://": "http://p2:8080"}

    def test_accepts_dict_with_none_values(self):
        proxy_dict = {"http": "http://p1:8080", "https": None}

        result = self.validator("proxy", proxy_dict)
        assert result == {"http://": "http://p1:8080", "https://": None}

    def test_rejects_dict_with_invalid_scheme(self):
        proxy_dict: dict[str, str | None] = {"ftp": "http://proxy:8080"}

        with pytest.raises(ValueError, match=r"Invalid proxy scheme.*ftp"):
            self.validator("proxy", proxy_dict)

    def test_rejects_dict_with_invalid_url(self):
        proxy_dict: dict[str, str | None] = {"http": "not-a-url"}

        with pytest.raises(ValueError, match="Proxy URL must include a scheme"):
            self.validator("proxy", proxy_dict)
