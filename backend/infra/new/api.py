from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello from TestLocal API!"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}