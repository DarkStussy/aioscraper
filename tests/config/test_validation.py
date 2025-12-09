from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

import pytest

from aioscraper.config.model_validator import validate, field
from aioscraper.config.field_validators import RangeValidator, LengthValidator, ChainValidator, CustomValidator
from aioscraper.exceptions import ConfigValidationError


class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class TestValidateDecorator:
    def test_validates_field_with_range_validator(self):
        @dataclass
        @validate
        class Config:
            port: int = field(default=8080, validator=RangeValidator(min=1, max=65535))

        config = Config(port=8080)
        assert config.port == 8080

        config = Config(port=1)
        assert config.port == 1

        config = Config(port=65535)
        assert config.port == 65535

        with pytest.raises(ConfigValidationError, match="port.*minimum is 1"):
            Config(port=0)

        with pytest.raises(ConfigValidationError, match="port.*maximum is 65535"):
            Config(port=65536)

    def test_validates_field_with_length_validator(self):
        @dataclass
        @validate
        class Config:
            api_key: str = field(default="", validator=LengthValidator(min=32))

        config = Config(api_key="a" * 32)
        assert len(config.api_key) == 32

        with pytest.raises(ConfigValidationError, match="api_key.*minimum is 32"):
            Config(api_key="short")

    def test_validates_multiple_fields(self):
        @dataclass
        @validate
        class Config:
            port: int = field(default=8080, validator=RangeValidator(min=1, max=65535))
            timeout: float = field(default=30.0, validator=RangeValidator(min=0.1, max=300.0))

        config = Config(port=3000, timeout=10.0)
        assert config.port == 3000
        assert config.timeout == 10.0

        with pytest.raises(ConfigValidationError, match="port"):
            Config(port=100000, timeout=10.0)

        with pytest.raises(ConfigValidationError, match="timeout"):
            Config(port=3000, timeout=500.0)

    def test_validates_with_chain_validator(self):
        @dataclass
        @validate
        class Config:
            workers: int = field(
                default=4,
                validator=ChainValidator([RangeValidator(min=1, max=100), CustomValidator(lambda x: x % 2 == 0)]),
            )

        config = Config(workers=4)
        assert config.workers == 4

        with pytest.raises(ConfigValidationError, match="workers.*minimum is 1"):
            Config(workers=0)

        with pytest.raises(ConfigValidationError, match="workers.*Custom validation failed"):
            Config(workers=3)

    def test_skips_validation_when_skip_validation_is_true(self):
        @dataclass
        @validate
        class Config:
            callback: Callable = field(default=lambda: None, skip_validation=True)

        config = Config(callback=lambda x: x * 2)
        assert callable(config.callback)

    def test_casts_string_to_int(self):
        @dataclass
        @validate
        class Config:
            port: int = 8080

        config = Config(port="3000")  # type: ignore
        assert config.port == 3000
        assert isinstance(config.port, int)

    def test_casts_string_to_float(self):
        @dataclass
        @validate
        class Config:
            timeout: float = 30.0

        config = Config(timeout="15.5")  # type: ignore
        assert config.timeout == 15.5
        assert isinstance(config.timeout, float)

    def test_casts_string_to_bool(self):
        @dataclass
        @validate
        class Config:
            enabled: bool = False

        for true_val in ["true", "True", "TRUE", "on", "yes", "1", "ok"]:
            config = Config(enabled=true_val)  # type: ignore
            assert config.enabled is True

        for false_val in ["false", "False", "FALSE", "0", "no"]:
            config = Config(enabled=false_val)  # type: ignore
            assert config.enabled is False

        with pytest.raises(ConfigValidationError, match="Cannot cast.*to bool"):
            Config(enabled="maybe")  # type: ignore

    def test_casts_string_to_decimal(self):
        @dataclass
        @validate
        class Config:
            price: Decimal = Decimal("0.00")

        config = Config(price="19.99")  # type: ignore
        assert config.price == Decimal("19.99")
        assert isinstance(config.price, Decimal)

    def test_casts_string_to_enum(self):
        @dataclass
        @validate
        class Config:
            color: Color = Color.RED

        config = Config(color="green")  # type: ignore
        assert config.color == Color.GREEN
        assert isinstance(config.color, Color)

        with pytest.raises(ConfigValidationError, match="Cannot cast.*to.*Color"):
            Config(color="yellow")  # type: ignore

    def test_handles_optional_types(self):
        @dataclass
        @validate
        class Config:
            timeout: float | None = None

        config = Config(timeout=None)
        assert config.timeout is None

        config = Config(timeout="10.5")  # type: ignore
        assert config.timeout == 10.5

    def test_handles_int_to_float_conversion(self):
        @dataclass
        @validate
        class Config:
            ratio: float = 1.0

        config = Config(ratio=42)
        assert config.ratio == 42.0
        assert isinstance(config.ratio, float)

    def test_validates_nested_dataclass(self):
        @dataclass
        @validate
        class ServerConfig:
            host: str = "localhost"
            port: int = field(default=8080, validator=RangeValidator(min=1, max=65535))

        @dataclass
        @validate
        class Config:
            server: ServerConfig = field(default_factory=lambda: ServerConfig())

        config = Config(server=ServerConfig(host="example.com", port=3000))
        assert config.server.host == "example.com"
        assert config.server.port == 3000

        with pytest.raises(ConfigValidationError):
            Config(server=ServerConfig(port=0))

    def test_preserves_original_post_init(self):
        @dataclass
        @validate
        class Config:
            value: int = 0

            def __post_init__(self):
                self.computed = self.value * 2

        config = Config(value="5")  # type: ignore
        assert config.value == 5
        assert config.computed == 10

    def test_raises_config_validation_error_with_field_name(self):
        @dataclass
        @validate
        class Config:
            port: int = field(default=8080, validator=RangeValidator(min=1, max=65535))

        with pytest.raises(ConfigValidationError) as exc_info:
            Config(port=100000)

        assert "Config.port" in str(exc_info.value)

    def test_handles_list_types(self):
        @dataclass
        @validate
        class Config:
            items: list[int] = field(default_factory=list)

        config = Config(items=[1, 2, 3])
        assert config.items == [1, 2, 3]

    def test_handles_dict_types(self):
        @dataclass
        @validate
        class Config:
            mapping: dict[str, int] = field(default_factory=dict)

        config = Config(mapping={"a": 1, "b": 2})
        assert config.mapping == {"a": 1, "b": 2}

    def test_handles_tuple_types(self):
        @dataclass
        @validate
        class Config:
            coords: tuple[float, float] = (0.0, 0.0)

        config = Config(coords=(1.5, 2.5))
        assert config.coords == (1.5, 2.5)


class TestFieldFunction:
    def test_creates_field_with_validator(self):
        @dataclass
        @validate
        class Config:
            port: int = field(default=8080, validator=RangeValidator(min=1, max=65535))

        config = Config()
        assert config.port == 8080

    def test_creates_field_with_default_factory(self):
        @dataclass
        @validate
        class Config:
            items: list[int] = field(default_factory=list)

        config1 = Config()
        config2 = Config()
        config1.items.append(1)

        assert config1.items == [1]
        assert config2.items == []

    def test_creates_field_with_metadata(self):
        @dataclass
        @validate
        class Config:
            value: int = field(default=0, metadata={"description": "Some value"})

        import dataclasses

        fields = dataclasses.fields(Config)
        value_field = next(f for f in fields if f.name == "value")
        assert value_field.metadata["description"] == "Some value"

    def test_creates_field_with_skip_validation(self):
        @dataclass
        @validate
        class Config:
            callback: Callable = field(default=lambda: None, skip_validation=True)

        config = Config()
        assert callable(config.callback)
