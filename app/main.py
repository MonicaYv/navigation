from fastapi import FastAPI

from .auth import router as auth_router
#from .company_auth import router as company_auth_router
from .user_maps import router as user_maps_router

app = FastAPI()

app.include_router(auth_router)
#app.include_router(company_auth_router)
app.include_router(user_maps_router)

@app.get("/")
def root():
    return {"message": "API is running!"}
