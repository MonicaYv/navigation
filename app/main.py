from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .auth import router as auth_router
#from .company_auth import router as company_auth_router
from .user_maps import router as user_maps_router
from .search_maps import router as search_maps_router
from .geofencing import router as geofencing_router

app = FastAPI()

app.mount("/test", StaticFiles(directory="static", html=True), name="static")

app.include_router(auth_router)
#app.include_router(company_auth_router)
app.include_router(user_maps_router)
app.include_router(search_maps_router)
app.include_router(geofencing_router)

@app.get("/")
def root():
    return {"message": "API is running!"}
