# 패턴과 대소문자 옵션별로 pydantic_core validator를 캐시한다. 잘못된 패턴은 예외, 불일치는 False다.
from functools import lru_cache

from pydantic_core import SchemaError, SchemaValidator, ValidationError, core_schema


class InvalidLorebookRegex(ValueError):
    pass


@lru_cache(maxsize=512)
def _regex_validator(pattern: str, case_sensitive: bool) -> SchemaValidator:
    try:
        # Keep Rust's linear-time regex engine and scope the legacy ignore-case
        # flag to the authored pattern. The cache key includes the case policy.
        regex_pattern = pattern if case_sensitive else f"(?i:{pattern})"
        return SchemaValidator(core_schema.str_schema(pattern=regex_pattern))
    except SchemaError as exc:
        raise InvalidLorebookRegex(
            "Invalid lorebook entry regular expression."
        ) from exc


def validate_regex(pattern: str) -> None:
    _regex_validator(pattern, False)


def regex_matches(pattern: str, text: str, *, case_sensitive: bool = False) -> bool:
    validator = _regex_validator(pattern, case_sensitive)
    try:
        validator.validate_python(text)
    except ValidationError:
        return False
    return True
