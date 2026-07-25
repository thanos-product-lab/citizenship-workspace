from pydantic import BaseModel


class CurrentUser(BaseModel):
    """The authenticated caller, derived from verified Clerk JWT claims.

    Claims only — there is no domain user record yet (case ownership is M2).
    """

    user_id: str
    session_id: str | None = None
    email: str | None = None
