from supabase import create_client, Client
import os
from dotenv import load_dotenv, find_dotenv

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from datetime import datetime

from models import Review, ReviewsRequest, GeneralResponse, rowRequest, llmReplyResponseformat
import logging

from transformers import pipeline
from typing import List, Optional

from constants import price_tags, hygiene_tags, services_tags, taste_tags

import google.genai as genai

import re

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance


logger = logging.getLogger(__name__)


# This is to find the path to .env file
dotenv_path = find_dotenv()
print("Found .env at:", dotenv_path)

# Load .env file
load_dotenv()

url = os.getenv("SUPABASE_URL", "https://ihhkylfceotjdslmxgvk.supabase.co")
key = os.getenv("SUPABASE_KEY", "sb_secret_PPwzbAcWIm69HTsGrh9pEw_ZzgHPU0A")
server_host = os.getenv("HOST", "0.0.0.0")
server_port = os.getenv("PORT", "8080")
llm_model = os.getenv("llm_model", "gemini-2.5-flash")
llm_api_key = os.getenv(
    "llm_api_key", "AIzaSyCOOVfKF5QgrextrcJ0B2Cjg9FUQQSgrXQ")

# print(url)

# Establishing Connection for supabase PostGreSql Database
supabaseClient = create_client(url, key)

# Creating a gemini Client for LLM usage
client = genai.Client(api_key=llm_api_key)


# response = supabaseClient.table('Sentimentdata').insert([{"location": "LA",  "rating": 2, "text": "Delivery late and items missing.", "date": "2025-06-20"},{"location": "LA",  "rating": 2, "text": "Delivery late and items missing.", "date": "2025-06-20"}]).execute()

# sentimentAnalyzer is for finding sentiment, and we are using
# -> "cardiffnlp/twitter-roberta-base-sentiment-latest" because it gives output
#  as -ve, +ve, neutral, and default one giving just +ve and -ve
sentimentAnalyzer = pipeline("sentiment-analysis",
                             model="cardiffnlp/twitter-roberta-base-sentiment-latest"
                             )

# Function Creation


# Function to find sentiment of the comment made by the Customer
def findSentiment(message: str) -> str:
    return sentimentAnalyzer(message)[0]["label"]

# Function to find topic regarding which customer has made the comment, we have used if-elif-else in order of decreasing priority
# so according to below function, customer gives most importance to 'price', then to 'hygiene', then to 'taste', then 'service', then any other thing


def findKeyword(message: str) -> str:
    message_lowerCase = message.lower()

    if any(topic in message_lowerCase for topic in price_tags):
        return "price"
    elif any(topic in message_lowerCase for topic in hygiene_tags):
        return "hygiene"
    elif any(topic in message_lowerCase for topic in taste_tags):
        return "taste"
    elif any(topic in message_lowerCase for topic in services_tags):
        return "service"
    else:
        return "others"


def generateLLMReply(comment: str, comment_sentiment: str) -> str:
    response = client.models.generate_content(
        model=llm_model, contents=f"""
        You are an experienced consultant, and I am providing you with a record of a table telling you about 

       1) Comment made by User on that restaurant.
       2) Sentiment which that comment is displaying.

       Give an Appropriate Reply which Restaurant can post for the comment made by the customer, for example

       -if a person's sentiment is neutral or negative our reply should apologise first , and then say something 
       which will tell the customer that future improvements will surely be made so that customer will surely comeback to try services again.

       -if a person's comment is positive, then our reply should thank and appreciate the positive comment and also signify that in future also we
       will provide better services

       here is the user's comment -> {comment} and sentiment he/she was showing -> {comment_sentiment}

       your output should be in exact format like -> *Your suggested reply for the customer's comment* #Your logic or reasons behind the reply you are giving#
       
       remember, the reply you are going to suggest ,that string is encloded in '*' and the reasoning_logic which you are going to give, that string is encloded in '#'
       
       example output -> "*Thank you for your replay , adn sorry for inconvenience* #I gave this reply becasue the comment was negative and I wanted to show how sad we are to not provide you with adequate services#"
              
       and your output should contain this json only nothing else.

       There are certain rules you need to follow while giving a reply-
       1) You reply should be polite and should not be rude

       Just follow this one rule
       """
    )
    
    print(response.text)
    return response.text


# API Creation

app = FastAPI()


@app.post("/ingest", response_model=GeneralResponse)
def insertReviewData(request: ReviewsRequest):
    try:
        # print(request.reviews[0].model_dump())
        reviews_data = [reviewVal.model_dump()
                        for reviewVal in request.reviews]
        for reviewVal in reviews_data:
            reviewVal["sentiment"] = findSentiment(reviewVal["text"])
            reviewVal["topic"] = findKeyword(reviewVal["text"])

        print(reviews_data)

        response = supabaseClient.table(
            'Sentimentdata').insert(reviews_data).execute()

        print(response)

        curTimeStamp = datetime.now().isoformat()

        return {
            "message": "reviews inserted successfully",
            "status": "200",
            "timestamp": curTimeStamp
        }
    except Exception as e:
        logger.error("Error Occured while inserting data inside database: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error occured while storing data: {str(e)}")


@app.get("/reviews/{id_val}")
def findCompleteRecord(id_val: int):
    try:
        logger.info("Started Finding Records")
        response = supabaseClient.table('Sentimentdata').select(
            '*').eq('id', id_val).execute()
        print(response.data[0])
        return response.data[0]
    except Exception as e:
        logger.error("Error Occured while fetching record from database: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error occured while storing data: {str(e)}")


@app.get("/reviews")
def filterRecordsFetch(location: Optional[str] = None, sentiment: Optional[str] = None, q: Optional[str] = None):
    try:
        logger.info("Started Filtering Records")

        query = supabaseClient.table('Sentimentdata').select('*')

        if location:
            query = query.eq('location', location)

        if sentiment:
            query = query.eq('sentiment', sentiment)

        if q:
            query = query.eq('topic', q)

        response = query.execute()

        logger.info("Records Filtered and Fetched Succesfully")
        return {"data": response.data}

    except Exception as e:
        logger.error(f"Error filtering records: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch records")


@app.post("/reviews/{id_val}/sugges-reply")
def generateAIReply(id_val: int) -> llmReplyResponseformat:
    logger.info("Fetching reply for customer's comment on the restaurant")
    
    table_record = supabaseClient.table("Sentimentdata").select("*").eq("id",id_val).execute()
    
    print(table_record)
    # print(generateLLMReply(table_record.data[0]["text"], table_record.data[0]["sentiment"]))
    final_LLM_response = generateLLMReply(table_record.data[0]["text"], table_record.data[0]["sentiment"])
    
    print(f"final_llm_response -> {final_LLM_response}")
    
    final_json_response=  final_LLM_response[final_LLM_response.find('{'):final_LLM_response.rfind('}')+1]
    LLM_reply = final_LLM_response[final_LLM_response.find('*')+1:final_LLM_response.rfind('*')]
    LLM_logic = final_LLM_response[final_LLM_response.find('#')+1:final_LLM_response.rfind('#')]
    
    print(f"--|-- {LLM_reply} and {LLM_logic}")
    
    recordSentiment=table_record.data[0]["sentiment"]
    recordTopic=table_record.data[0]["topic"]
    
    insert_obj = {
        "llmReply":LLM_reply,
        "replyLogic":LLM_logic
    }
    
    supabaseClient.table('Sentimentdata').update(insert_obj).eq("id", id_val).execute()
    
    return {
        "reply":LLM_reply,
        "logic":LLM_logic,
        "sentiment":recordSentiment,
        "topic":recordTopic
    }
    
    # return generateLLMReply(table_record.data[0]["text"], table_record.data[0]["sentiment"])

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=server_host,
        port=server_port,
        reload=False
    )
