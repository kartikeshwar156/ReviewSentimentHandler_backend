from pydantic import BaseModel, Field
from typing import List, Optional

class Review(BaseModel):
   location: str
   rating: int = Field(..., ge=1, le=5)  # Rating between 1-5
   text: str
   date: str
   sentiment: Optional[str] = None
   topic: Optional[str] = None
   
class ReviewsRequest(BaseModel):
   reviews: List[Review]
   
class GeneralResponse(BaseModel):
   message: str
   status: str
   timestamp: str
   
class rowRequest(BaseModel):
   id: int
   
class llmReplyResponseformat(BaseModel):
   reply: str
   logic: str
   sentiment: str
   topic: str
   