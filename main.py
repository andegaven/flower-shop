from fastapi import FastAPI, HTTPException
import uvicorn
from pydantic import BaseModel


app = FastAPI()





if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
