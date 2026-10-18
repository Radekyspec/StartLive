from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PkPrecheckResult:
    """A code-zero precheck projection, not a guarantee of PK eligibility."""
    show_type: int
    title: str = field(repr=False)
    content: str = field(repr=False)
    confirm_content: str = field(repr=False)

    @property
    def intercepted(self) -> bool:
        return self.show_type == 1
