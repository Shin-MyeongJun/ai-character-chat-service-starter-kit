# 대소문자 무시 패턴을 pydantic_core validator로 컴파일해 캐시한다. 잘못된 패턴은 예외, 불일치는 False다.
from functools import lru_cache

from pydantic_core import SchemaError, SchemaValidator, ValidationError, core_schema


class InvalidLorebookRegex(ValueError):
    pass


@lru_cache(maxsize=512)
def _regex_validator(pattern: str) -> SchemaValidator:
    try:
        # pydantic-core uses Rust's linear-time regex engine. The scoped flag keeps
        # lorebook matching case-insensitive without Python re backtracking risks.
        return SchemaValidator(core_schema.str_schema(pattern=f"(?i:{pattern})"))
    except SchemaError as exc:
        raise InvalidLorebookRegex(
            "Invalid lorebook entry regular expression."
        ) from exc


def validate_regex(pattern: str) -> None:
    _regex_validator(pattern)


def regex_matches(pattern: str, text: str) -> bool:
    validator = _regex_validator(pattern)
    try:
        validator.validate_python(text)
    except ValidationError:
        return False
    return True
