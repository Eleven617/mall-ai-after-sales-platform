from pydantic import BaseModel, Field, field_validator


class CustomerLoginRequest(BaseModel):
    """Credentials accepted only for forwarding to the Java member-login API."""

    username: str = Field(min_length=1, max_length=64, examples=["test"])
    password: str = Field(min_length=1, max_length=128, repr=False)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("用户名不能为空。")
        return normalized


class MemberProfile(BaseModel):
    """The small, browser-safe identity view returned by Java authentication."""

    member_id: int = Field(gt=0)
    username: str = Field(min_length=1, max_length=64)


class CustomerLoginResponse(BaseModel):
    """Java-issued Bearer credential plus a deliberately small member profile."""

    authorization: str = Field(min_length=8)
    member: MemberProfile
