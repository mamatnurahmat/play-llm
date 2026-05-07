from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    # Operator add digunakan agar pesan baru di-append ke list yang sudah ada
    messages: Annotated[Sequence[BaseMessage], operator.add]
